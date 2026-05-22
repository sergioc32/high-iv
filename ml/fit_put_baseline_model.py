"""Fit the first put-only baseline models for expected return on risk."""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRAINING_DATASET = PROJECT_ROOT / "ml" / "training_dataset.csv"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "ml" / "reports"
DEFAULT_MD_REPORT = "put_model_baseline_fit.md"
DEFAULT_METRICS_CSV = "put_model_baseline_fit_metrics.csv"
DEFAULT_PREDICTIONS_CSV = "put_model_baseline_predictions.csv"
TARGET_STRATEGY = "put_credit_spread"
KNN_FEATURES = [
    "dte",
    "width",
    "premium_per_width",
    "max_loss",
    "risk_reward_ratio",
    "short_delta",
    "moneyness_pct",
    "distance_to_short_strike_pct",
    "width_pct_of_stock",
    "premium_pct_of_width",
    "delta_distance_from_target",
]
LINEAR_CORE_FEATURES = [
    "dte",
    "premium_per_width",
    "max_loss",
    "risk_reward_ratio",
    "short_delta",
    "moneyness_pct",
    "distance_to_short_strike_pct",
    "delta_distance_from_target",
]
LINEAR_PLUS_ALIGNMENT_FEATURES = LINEAR_CORE_FEATURES + ["strategy_alignment_score"]
K_CANDIDATES = [3, 5, 7]
RIDGE_LAMBDAS = [0.1, 1.0, 5.0, 10.0]


@dataclass(frozen=True)
class Metrics:
    mae: float
    rmse: float
    directional_accuracy: float
    count: int


def load_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def parse_float(value: object) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def safe_mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def format_float(value: float, precision: int = 6) -> str:
    return f"{value:.{precision}f}"


def sign_flag(value: float) -> int:
    return 1 if value >= 0 else 0


def evaluate_predictions(actuals: list[float], predictions: list[float]) -> Metrics:
    if not actuals or not predictions or len(actuals) != len(predictions):
        return Metrics(mae=0.0, rmse=0.0, directional_accuracy=0.0, count=0)
    errors = [pred - actual for actual, pred in zip(actuals, predictions, strict=True)]
    mae = safe_mean([abs(error) for error in errors])
    rmse = math.sqrt(safe_mean([error * error for error in errors]))
    directional_hits = sum(
        1
        for actual, pred in zip(actuals, predictions, strict=True)
        if sign_flag(actual) == sign_flag(pred)
    )
    return Metrics(
        mae=mae,
        rmse=rmse,
        directional_accuracy=directional_hits / len(actuals),
        count=len(actuals),
    )


def fit_linear_alignment_baseline(
    rows: list[dict[str, str]],
) -> tuple[float, float, float]:
    train_mean = safe_mean(
        [parse_float(row["realized_return_on_risk"]) or 0.0 for row in rows]
    )
    pairs = []
    for row in rows:
        alignment = parse_float(row.get("strategy_alignment_score"))
        target = parse_float(row.get("realized_return_on_risk"))
        if alignment is None or target is None:
            continue
        pairs.append((alignment, target))
    if len(pairs) < 2:
        return 0.0, train_mean, train_mean
    x_mean = safe_mean([item[0] for item in pairs])
    y_mean = safe_mean([item[1] for item in pairs])
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    denominator = sum((x - x_mean) ** 2 for x, _ in pairs)
    if denominator == 0:
        return 0.0, y_mean, train_mean
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    return slope, intercept, train_mean


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a small dense linear system with Gaussian elimination."""
    size = len(vector)
    augmented = [row[:] + [rhs] for row, rhs in zip(matrix, vector, strict=True)]
    for pivot_index in range(size):
        pivot_row = max(
            range(pivot_index, size),
            key=lambda row_index: abs(augmented[row_index][pivot_index]),
        )
        if abs(augmented[pivot_row][pivot_index]) < 1e-12:
            raise ValueError("Singular matrix encountered while fitting ridge model.")
        if pivot_row != pivot_index:
            augmented[pivot_index], augmented[pivot_row] = (
                augmented[pivot_row],
                augmented[pivot_index],
            )
        pivot_value = augmented[pivot_index][pivot_index]
        for column in range(pivot_index, size + 1):
            augmented[pivot_index][column] /= pivot_value
        for row_index in range(size):
            if row_index == pivot_index:
                continue
            factor = augmented[row_index][pivot_index]
            if factor == 0:
                continue
            for column in range(pivot_index, size + 1):
                augmented[row_index][column] -= factor * augmented[pivot_index][column]
    return [augmented[row_index][-1] for row_index in range(size)]


def predict_alignment_baseline(
    rows: list[dict[str, str]], slope: float, intercept: float, fallback: float
) -> list[float]:
    output: list[float] = []
    for row in rows:
        alignment = parse_float(row.get("strategy_alignment_score"))
        output.append(
            intercept + slope * alignment if alignment is not None else fallback
        )
    return output


def build_feature_stats(
    rows: list[dict[str, str]], feature_names: list[str]
) -> dict[str, tuple[float, float]]:
    stats: dict[str, tuple[float, float]] = {}
    for feature in feature_names:
        values = [
            parsed
            for row in rows
            if (parsed := parse_float(row.get(feature))) is not None
        ]
        if not values:
            stats[feature] = (0.0, 1.0)
            continue
        center = median(values)
        variance = safe_mean([(value - center) ** 2 for value in values])
        scale = math.sqrt(variance) or 1.0
        stats[feature] = (center, scale)
    return stats


def encode_row(
    row: dict[str, str],
    feature_names: list[str],
    feature_stats: dict[str, tuple[float, float]],
) -> list[float]:
    encoded: list[float] = []
    for feature in feature_names:
        center, scale = feature_stats[feature]
        value = parse_float(row.get(feature))
        if value is None:
            value = center
        encoded.append((value - center) / scale)
    return encoded


def fit_knn_model(
    rows: list[dict[str, str]], feature_names: list[str]
) -> tuple[list[tuple[list[float], float]], dict[str, tuple[float, float]]]:
    feature_stats = build_feature_stats(rows, feature_names)
    training_vectors: list[tuple[list[float], float]] = []
    for row in rows:
        target = parse_float(row.get("realized_return_on_risk"))
        if target is None:
            continue
        training_vectors.append((encode_row(row, feature_names, feature_stats), target))
    return training_vectors, feature_stats


def build_design_matrix(
    rows: list[dict[str, str]],
    feature_names: list[str],
    feature_stats: dict[str, tuple[float, float]],
) -> list[list[float]]:
    return [[1.0] + encode_row(row, feature_names, feature_stats) for row in rows]


def fit_ridge_regression(
    rows: list[dict[str, str]], feature_names: list[str], ridge_lambda: float
) -> tuple[list[float], dict[str, tuple[float, float]]]:
    feature_stats = build_feature_stats(rows, feature_names)
    design_matrix = build_design_matrix(rows, feature_names, feature_stats)
    targets = [parse_float(row["realized_return_on_risk"]) or 0.0 for row in rows]
    column_count = len(feature_names) + 1
    xtx = [[0.0 for _ in range(column_count)] for _ in range(column_count)]
    xty = [0.0 for _ in range(column_count)]
    for row_vector, target in zip(design_matrix, targets, strict=True):
        for i in range(column_count):
            xty[i] += row_vector[i] * target
            for j in range(column_count):
                xtx[i][j] += row_vector[i] * row_vector[j]
    for index in range(1, column_count):
        xtx[index][index] += ridge_lambda
    coefficients = solve_linear_system(xtx, xty)
    return coefficients, feature_stats


def predict_ridge_regression(
    rows: list[dict[str, str]],
    feature_names: list[str],
    feature_stats: dict[str, tuple[float, float]],
    coefficients: list[float],
) -> list[float]:
    output: list[float] = []
    for row in rows:
        vector = [1.0] + encode_row(row, feature_names, feature_stats)
        output.append(
            sum(
                weight * value
                for weight, value in zip(coefficients, vector, strict=True)
            )
        )
    return output


def euclidean_distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def predict_knn(
    rows: list[dict[str, str]],
    training_vectors: list[tuple[list[float], float]],
    feature_names: list[str],
    feature_stats: dict[str, tuple[float, float]],
    k: int,
) -> list[float]:
    if not training_vectors:
        return [0.0 for _ in rows]
    output: list[float] = []
    for row in rows:
        vector = encode_row(row, feature_names, feature_stats)
        neighbors = sorted(
            (
                (euclidean_distance(vector, train_vector), target)
                for train_vector, target in training_vectors
            ),
            key=lambda item: item[0],
        )[: min(k, len(training_vectors))]
        weights = [1.0 / (distance + 1e-6) for distance, _ in neighbors]
        weighted_sum = sum(
            weight * target
            for weight, (_, target) in zip(weights, neighbors, strict=True)
        )
        output.append(weighted_sum / sum(weights))
    return output


def normalize_model_score(
    prediction: float, low_anchor: float, high_anchor: float
) -> float:
    if high_anchor <= low_anchor:
        return 50.0
    scaled = (prediction - low_anchor) / (high_anchor - low_anchor)
    return max(0.0, min(100.0, scaled * 100.0))


def build_predictions_rows(
    rows: list[dict[str, str]],
    mean_predictions: list[float],
    alignment_predictions: list[float],
    model_predictions: list[float],
    low_anchor: float,
    high_anchor: float,
    model_score_version: str,
) -> list[list[str]]:
    output: list[list[str]] = []
    for row, mean_pred, alignment_pred, model_pred in zip(
        rows, mean_predictions, alignment_predictions, model_predictions, strict=True
    ):
        output.append(
            [
                row.get("trade_id", ""),
                row.get("symbol", ""),
                row.get("time_split_group", ""),
                row.get("entry_date", ""),
                row.get("close_date", ""),
                row.get("realized_return_on_risk", ""),
                format_float(mean_pred),
                format_float(alignment_pred),
                format_float(model_pred),
                format_float(
                    normalize_model_score(model_pred, low_anchor, high_anchor),
                    precision=2,
                ),
                model_score_version,
            ]
        )
    return output


def render_markdown_report(
    *,
    dataset_path: Path,
    row_count: int,
    split_counts: dict[str, int],
    best_model_name: str,
    best_model_detail: str,
    low_anchor: float,
    high_anchor: float,
    validation_metrics: dict[str, Metrics],
    test_metrics: dict[str, Metrics],
) -> str:
    lines = [
        "# Put Baseline Model Fit",
        "",
        f"- Dataset: `{dataset_path}`",
        f"- Strategy: `{TARGET_STRATEGY}`",
        f"- Rows used: `{row_count}`",
        f"- Split counts: `{split_counts}`",
        f"- k-NN features: `{', '.join(KNN_FEATURES)}`",
        f"- Linear-core features: `{', '.join(LINEAR_CORE_FEATURES)}`",
        f"- Best ML candidate from validation: `{best_model_name}` ({best_model_detail})",
        f"- Model-score normalization anchors: low=`{low_anchor:.4f}`, high=`{high_anchor:.4f}`",
        "",
        "## Validation Metrics",
        "",
        "| Model | Rows | MAE | RMSE | Directional Accuracy |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, metrics in validation_metrics.items():
        lines.append(
            f"| {name} | {metrics.count} | {metrics.mae:.4f} | {metrics.rmse:.4f} | {metrics.directional_accuracy:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Test Metrics",
            "",
            "| Model | Rows | MAE | RMSE | Directional Accuracy |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for name, metrics in test_metrics.items():
        lines.append(
            f"| {name} | {metrics.count} | {metrics.mae:.4f} | {metrics.rmse:.4f} | {metrics.directional_accuracy:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `global_mean` is the naive benchmark using the train-set average return on risk.",
            "- `alignment_only` uses the existing alignment score by itself as a one-feature baseline.",
            "- `put_knn`, `put_linear_core`, and `put_linear_plus_alignment` are the current ML-style candidate models.",
            "- `put_linear_plus_alignment` is allowed to use the alignment score as an input feature so we can test whether ML adds value on top of the heuristic you already trust.",
            "- This fit is put-only on purpose; call-side supervised fitting should wait for enough trusted closed history.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def build_metrics_csv_rows(
    section: str, metrics_map: dict[str, Metrics]
) -> list[list[str]]:
    rows: list[list[str]] = []
    for model_name, metrics in metrics_map.items():
        rows.extend(
            [
                [section, model_name, "count", str(metrics.count)],
                [section, model_name, "mae", format_float(metrics.mae)],
                [section, model_name, "rmse", format_float(metrics.rmse)],
                [
                    section,
                    model_name,
                    "directional_accuracy",
                    format_float(metrics.directional_accuracy),
                ],
            ]
        )
    return rows


def run_put_baseline_fit(
    dataset_path: Path = DEFAULT_TRAINING_DATASET,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
) -> dict[str, Path]:
    _, rows = load_csv_rows(dataset_path)
    put_rows = [
        row
        for row in rows
        if (row.get("strategy_id") or "").strip() == TARGET_STRATEGY
        and parse_float(row.get("realized_return_on_risk")) is not None
    ]
    train_rows = [
        row
        for row in put_rows
        if (row.get("time_split_group") or "").strip() == "train"
    ]
    validation_rows = [
        row
        for row in put_rows
        if (row.get("time_split_group") or "").strip() == "validation"
    ]
    test_rows = [
        row for row in put_rows if (row.get("time_split_group") or "").strip() == "test"
    ]
    if not train_rows or not validation_rows or not test_rows:
        raise ValueError(
            "Put baseline fit requires populated train, validation, and test splits."
        )

    train_targets = [
        parse_float(row["realized_return_on_risk"]) or 0.0 for row in train_rows
    ]
    validation_targets = [
        parse_float(row["realized_return_on_risk"]) or 0.0 for row in validation_rows
    ]
    test_targets = [
        parse_float(row["realized_return_on_risk"]) or 0.0 for row in test_rows
    ]

    global_mean = safe_mean(train_targets)
    slope, intercept, alignment_fallback = fit_linear_alignment_baseline(train_rows)
    training_vectors, knn_feature_stats = fit_knn_model(train_rows, KNN_FEATURES)
    linear_core_feature_stats = build_feature_stats(train_rows, LINEAR_CORE_FEATURES)
    linear_plus_feature_stats = build_feature_stats(
        train_rows, LINEAR_PLUS_ALIGNMENT_FEATURES
    )

    best_model_name = ""
    best_model_detail = ""
    best_validation_mae = float("inf")
    best_model_version = ""
    best_validation_model_predictions: list[float] = []
    best_test_model_predictions: list[float] = []

    candidate_validation_predictions: dict[str, list[float]] = {}
    candidate_test_predictions: dict[str, list[float]] = {}

    for k in K_CANDIDATES:
        model_name = "put_knn"
        validation_predictions = predict_knn(
            validation_rows, training_vectors, KNN_FEATURES, knn_feature_stats, k
        )
        test_predictions = predict_knn(
            test_rows, training_vectors, KNN_FEATURES, knn_feature_stats, k
        )
        metrics = evaluate_predictions(validation_targets, validation_predictions)
        candidate_key = f"{model_name}_k{k}"
        candidate_validation_predictions[candidate_key] = validation_predictions
        candidate_test_predictions[candidate_key] = test_predictions
        if metrics.mae < best_validation_mae:
            best_validation_mae = metrics.mae
            best_model_name = model_name
            best_model_detail = f"k={k}"
            best_model_version = f"put_knn_ror_v1_k{k}"
            best_validation_model_predictions = validation_predictions
            best_test_model_predictions = test_predictions

    for ridge_lambda in RIDGE_LAMBDAS:
        core_coefficients, _ = fit_ridge_regression(
            train_rows, LINEAR_CORE_FEATURES, ridge_lambda
        )
        validation_predictions = predict_ridge_regression(
            validation_rows,
            LINEAR_CORE_FEATURES,
            linear_core_feature_stats,
            core_coefficients,
        )
        test_predictions = predict_ridge_regression(
            test_rows,
            LINEAR_CORE_FEATURES,
            linear_core_feature_stats,
            core_coefficients,
        )
        metrics = evaluate_predictions(validation_targets, validation_predictions)
        candidate_key = f"put_linear_core_l{ridge_lambda:g}"
        candidate_validation_predictions[candidate_key] = validation_predictions
        candidate_test_predictions[candidate_key] = test_predictions
        if metrics.mae < best_validation_mae:
            best_validation_mae = metrics.mae
            best_model_name = "put_linear_core"
            best_model_detail = f"lambda={ridge_lambda:g}"
            best_model_version = f"put_linear_core_ror_v1_l{ridge_lambda:g}"
            best_validation_model_predictions = validation_predictions
            best_test_model_predictions = test_predictions

        plus_coefficients, _ = fit_ridge_regression(
            train_rows, LINEAR_PLUS_ALIGNMENT_FEATURES, ridge_lambda
        )
        validation_predictions = predict_ridge_regression(
            validation_rows,
            LINEAR_PLUS_ALIGNMENT_FEATURES,
            linear_plus_feature_stats,
            plus_coefficients,
        )
        test_predictions = predict_ridge_regression(
            test_rows,
            LINEAR_PLUS_ALIGNMENT_FEATURES,
            linear_plus_feature_stats,
            plus_coefficients,
        )
        metrics = evaluate_predictions(validation_targets, validation_predictions)
        candidate_key = f"put_linear_plus_alignment_l{ridge_lambda:g}"
        candidate_validation_predictions[candidate_key] = validation_predictions
        candidate_test_predictions[candidate_key] = test_predictions
        if metrics.mae < best_validation_mae:
            best_validation_mae = metrics.mae
            best_model_name = "put_linear_plus_alignment"
            best_model_detail = f"lambda={ridge_lambda:g}"
            best_model_version = f"put_linear_plus_alignment_ror_v1_l{ridge_lambda:g}"
            best_validation_model_predictions = validation_predictions
            best_test_model_predictions = test_predictions

    validation_global = [global_mean] * len(validation_rows)
    validation_alignment = predict_alignment_baseline(
        validation_rows, slope, intercept, alignment_fallback
    )
    test_global = [global_mean] * len(test_rows)
    test_alignment = predict_alignment_baseline(
        test_rows, slope, intercept, alignment_fallback
    )

    validation_metrics = {
        "global_mean": evaluate_predictions(validation_targets, validation_global),
        "alignment_only": evaluate_predictions(
            validation_targets, validation_alignment
        ),
        "put_knn": min(
            (
                evaluate_predictions(validation_targets, predictions)
                for key, predictions in candidate_validation_predictions.items()
                if key.startswith("put_knn_")
            ),
            key=lambda metrics: metrics.mae,
        ),
        "put_linear_core": min(
            (
                evaluate_predictions(validation_targets, predictions)
                for key, predictions in candidate_validation_predictions.items()
                if key.startswith("put_linear_core_")
            ),
            key=lambda metrics: metrics.mae,
        ),
        "put_linear_plus_alignment": min(
            (
                evaluate_predictions(validation_targets, predictions)
                for key, predictions in candidate_validation_predictions.items()
                if key.startswith("put_linear_plus_alignment_")
            ),
            key=lambda metrics: metrics.mae,
        ),
    }
    test_metrics = {
        "global_mean": evaluate_predictions(test_targets, test_global),
        "alignment_only": evaluate_predictions(test_targets, test_alignment),
        "put_knn": evaluate_predictions(
            test_targets,
            candidate_test_predictions[
                min(
                    (
                        key
                        for key in candidate_validation_predictions
                        if key.startswith("put_knn_")
                    ),
                    key=lambda key: (
                        evaluate_predictions(
                            validation_targets, candidate_validation_predictions[key]
                        ).mae
                    ),
                )
            ],
        ),
        "put_linear_core": evaluate_predictions(
            test_targets,
            candidate_test_predictions[
                min(
                    (
                        key
                        for key in candidate_validation_predictions
                        if key.startswith("put_linear_core_")
                    ),
                    key=lambda key: (
                        evaluate_predictions(
                            validation_targets, candidate_validation_predictions[key]
                        ).mae
                    ),
                )
            ],
        ),
        "put_linear_plus_alignment": evaluate_predictions(
            test_targets,
            candidate_test_predictions[
                min(
                    (
                        key
                        for key in candidate_validation_predictions
                        if key.startswith("put_linear_plus_alignment_")
                    ),
                    key=lambda key: (
                        evaluate_predictions(
                            validation_targets, candidate_validation_predictions[key]
                        ).mae
                    ),
                )
            ],
        ),
    }

    low_anchor = quantile(train_targets, 0.10)
    high_anchor = quantile(train_targets, 0.90)

    markdown = render_markdown_report(
        dataset_path=dataset_path,
        row_count=len(put_rows),
        split_counts={
            "train": len(train_rows),
            "validation": len(validation_rows),
            "test": len(test_rows),
        },
        best_model_name=best_model_name,
        best_model_detail=best_model_detail,
        low_anchor=low_anchor,
        high_anchor=high_anchor,
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
    )
    metrics_rows = build_metrics_csv_rows(
        "validation", validation_metrics
    ) + build_metrics_csv_rows("test", test_metrics)
    prediction_rows = build_predictions_rows(
        validation_rows + test_rows,
        validation_global + test_global,
        validation_alignment + test_alignment,
        best_validation_model_predictions + best_test_model_predictions,
        low_anchor,
        high_anchor,
        best_model_version,
    )

    markdown_path = reports_dir / DEFAULT_MD_REPORT
    metrics_path = reports_dir / DEFAULT_METRICS_CSV
    predictions_path = reports_dir / DEFAULT_PREDICTIONS_CSV
    write_text(markdown_path, markdown)
    write_csv(metrics_path, ["section", "model", "metric", "value"], metrics_rows)
    write_csv(
        predictions_path,
        [
            "trade_id",
            "symbol",
            "time_split_group",
            "entry_date",
            "close_date",
            "actual_realized_return_on_risk",
            "global_mean_prediction",
            "alignment_only_prediction",
            "predicted_return_on_risk",
            "model_score",
            "model_score_version",
        ],
        prediction_rows,
    )
    return {
        "markdown_path": markdown_path,
        "metrics_path": metrics_path,
        "predictions_path": predictions_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=DEFAULT_TRAINING_DATASET,
        help="Path to training_dataset.csv",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory for baseline-fit report artifacts",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = run_put_baseline_fit(args.dataset_path, args.reports_dir)
    print(f"Put baseline markdown report written to: {outputs['markdown_path']}")
    print(f"Put baseline metrics CSV written to: {outputs['metrics_path']}")
    print(f"Put baseline predictions CSV written to: {outputs['predictions_path']}")


if __name__ == "__main__":
    main()
