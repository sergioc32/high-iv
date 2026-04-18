import hashlib
import json
import os
import time
from datetime import datetime
from typing import Any

DEFAULT_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "cache"
)


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _key_to_path(cache_dir: str, key: str) -> str:
    hashed = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return os.path.join(cache_dir, f"{hashed}.json")


def get(
    key: str, ttl_seconds: int, cache_dir: str | None = None, same_day: bool = False
) -> Any | None:
    """Retrieve cached data if not expired. Returns None when missing/expired.
    When same_day=True, cached entries from a previous calendar day are treated as expired
    regardless of TTL. Useful for data that changes day-over-day (e.g., DTE).
    """
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    _ensure_dir(cache_dir)

    path = _key_to_path(cache_dir, key)
    if not os.path.exists(path):
        return None

    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        ts = payload.get("timestamp")
        if ts is None:
            return None
        # Enforce TTL expiry
        if time.time() - ts > ttl_seconds:
            return None
        # Enforce daily boundary expiry if requested
        if same_day:
            cached_day = datetime.fromtimestamp(ts).date()
            if cached_day != datetime.now().date():
                return None
        return payload.get("data")
    except Exception:
        return None


def set(key: str, data: Any, cache_dir: str | None = None) -> None:
    """Persist data in cache with current timestamp."""
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    _ensure_dir(cache_dir)

    path = _key_to_path(cache_dir, key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": time.time(), "data": data}, f)
    except Exception:
        # Fail silently; caching is a best-effort optimization
        pass


def clear_all(cache_dir: str | None = None) -> int:
    """Clear all cache files. Returns count of files deleted."""
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR

    if not os.path.exists(cache_dir):
        return 0

    count = 0
    try:
        for filename in os.listdir(cache_dir):
            filepath = os.path.join(cache_dir, filename)
            if os.path.isfile(filepath) and filename.endswith(".json"):
                os.remove(filepath)
                count += 1
    except Exception as e:
        print(f"Warning: Failed to clear cache: {e}")

    return count


def clear_stale_daily(cache_dir: str | None = None) -> int:
    """Clear cache entries from previous calendar days. Returns count of files deleted."""
    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR

    if not os.path.exists(cache_dir):
        return 0

    today = datetime.now().date()
    count = 0

    try:
        for filename in os.listdir(cache_dir):
            filepath = os.path.join(cache_dir, filename)
            if os.path.isfile(filepath) and filename.endswith(".json"):
                try:
                    with open(filepath, encoding="utf-8") as f:
                        payload = json.load(f)
                    ts = payload.get("timestamp")
                    if ts:
                        cache_date = datetime.fromtimestamp(ts).date()
                        if cache_date < today:
                            os.remove(filepath)
                            count += 1
                except Exception:
                    # If we can't read the file, leave it alone
                    pass
    except Exception as e:
        print(f"Warning: Failed to clear stale cache: {e}")

    return count
