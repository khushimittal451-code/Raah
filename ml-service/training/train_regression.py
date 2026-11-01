"""Provisional named regressors and persistence baseline; validation only, never test.

No official syllabus evidence exists yet. Only the two user-named methods are enabled.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import time
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml-service"))
from app.schemas import LabeledTrafficRecord  # noqa: E402
from training.prepare_data import REGRESSION_FEATURES, digest, require  # noqa: E402
from training.preprocessing import build_preprocessor, prediction_frame  # noqa: E402

TASK = "future_wait_regression"
TARGET = "future_wait_seconds"
MODEL_NAMES = ("linear_regression", "polynomial_degree2")
STATUS = "PROVISIONAL_UNVERIFIED"


def build_regressor(name):
    if name not in MODEL_NAMES:
        raise ValueError("Only provisional linear_regression and polynomial_degree2 are enabled; no other method is authorized")
    preprocessing = build_preprocessor(TASK, numeric_scaling="standard")
    if name == "polynomial_degree2":
        # Expand numeric inputs only, before their scaler; never phase dummy columns.
        numeric = preprocessing.named_steps["columns"].transformers[0][1]
        numeric.steps.insert(1, ("polynomial", PolynomialFeatures(degree=2, include_bias=False)))
    return Pipeline([("preprocessing", preprocessing), ("regressor", LinearRegression())])


def persistence_prediction(frame):
    values = pd.to_numeric(frame["mean_wait_seconds"], errors="raise").to_numpy(dtype=float)
    require(np.isfinite(values).all(), "baseline requires finite current observed wait")
    return values.copy()


def metrics(actual, predicted):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    require(actual.ndim == predicted.ndim == 1 and actual.shape == predicted.shape and len(actual) > 0, "invalid prediction shape")
    require(np.isfinite(actual).all() and np.isfinite(predicted).all(), "nonfinite actual/predicted values")
    r2 = float(r2_score(actual, predicted)) if len(actual) >= 2 and np.var(actual) > 0 else None
    return {"validation_mae_seconds": float(mean_absolute_error(actual, predicted)),
            "validation_rmse_seconds": float(np.sqrt(mean_squared_error(actual, predicted))),
            "validation_r2": r2}


def load_train_validation(splits_dir):
    """Read exactly two approved data files; never open/hash/transform test.csv."""
    splits_dir = Path(splits_dir).resolve()
    manifest_path = splits_dir / "split_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest["seed"] == 57 and manifest["prediction_horizon_seconds"] == 60, "unexpected seed or horizon")
    require(manifest["group_column"] == "run_id", "group policy must be run_id")
    require(manifest["checks"]["future_labels_exact_same_group"], "future-label provenance audit missing")
    require(tuple(manifest["features"][TASK]) == REGRESSION_FEATURES, "regression feature policy mismatch")
    frames = {}
    hashes = {"split_manifest.json": digest(manifest_path)}
    for name in ("train", "validation"):
        info = manifest["splits"][name]
        require(info["file"] == f"{name}.csv", "unexpected data file; refusing access")
        path = (splits_dir / info["file"]).resolve()
        require(path.parent == splits_dir and path.name == f"{name}.csv", "data path escapes approved train/validation files")
        require(digest(path) == info["sha256"], f"{name} split hash mismatch")
        frame = pd.read_csv(path)
        require(list(frame.columns) == list(LabeledTrafficRecord.model_fields), "unexpected raw columns")
        require(len(frame) == info["rows"] and frame.run_id.nunique() == info["groups"] and set(frame.run_id) == set(info["run_ids"]), "manifest membership/count mismatch")
        # Revalidate canonical current-label/range constraints without any test access.
        for row in frame.to_dict("records"):
            if pd.isna(row["mean_speed_kmh"]):
                row["mean_speed_kmh"] = None
            LabeledTrafficRecord.model_validate(row)
        require(frame[TARGET].notna().all(), "missing future target")
        frames[name] = frame
        hashes[path.name] = digest(path)
    train_ids, validation_ids = set(frames["train"].run_id), set(frames["validation"].run_id)
    require(not train_ids & validation_ids, "training/validation run overlap")
    test_ids = set(manifest["splits"]["test"]["run_ids"])  # IDs only, no test data access.
    require(not test_ids & (train_ids | validation_ids), "declared test group overlaps development groups")
    return frames, manifest, hashes


def evaluate_frames(train, validation):
    """Fixed comparisons only. Targets never enter X; validation never fits anything."""
    required = set(REGRESSION_FEATURES) | {TARGET, "run_id", "timestamp_seconds", "intersection_id", "approach_id"}
    for name, frame in (("train", train), ("validation", validation)):
        require(isinstance(frame, pd.DataFrame) and len(frame) > 0, f"empty/non-DataFrame {name}")
        require(required <= set(frame.columns), f"missing required features or audit metadata: {name}")
    require(not set(train.run_id) & set(validation.run_id), "run group overlap")
    X_train, X_validation = prediction_frame(train, TASK), prediction_frame(validation, TASK)
    y_train, y_validation = train[TARGET].to_numpy(dtype=float), validation[TARGET].to_numpy(dtype=float)
    require(np.isfinite(y_train).all() and np.isfinite(y_validation).all(), "nonfinite targets")
    prediction_tables, comparisons, per_run, fitted_models = [], [], [], {}
    for name in ("last_observed_wait", *MODEL_NAMES):
        caught = []
        if name == "last_observed_wait":
            train_seconds = 0.0  # No trainable parameters, not a timed model fit.
            started = time.perf_counter()
            prediction = persistence_prediction(validation)
            predict_seconds = time.perf_counter() - started
            output_count, rank = 1, None
        else:
            model = build_regressor(name)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                started = time.perf_counter()
                model.fit(X_train, y_train)
                train_seconds = time.perf_counter() - started
            state = joblib.hash(model)
            started = time.perf_counter()
            prediction = model.predict(X_validation)
            predict_seconds = time.perf_counter() - started
            require(joblib.hash(model) == state, "validation prediction modified fitted state")
            output_count = len(model.named_steps["preprocessing"].get_feature_names_out())
            rank = int(model.named_steps["regressor"].rank_)
            fitted_models[name] = model
        result = metrics(y_validation, prediction)
        comparisons.append({"model": name, "status": "REFERENCE_BASELINE" if name == "last_observed_wait" else STATUS,
                            "evaluation_split": "validation", **result,
                            "training_seconds": train_seconds, "prediction_seconds": predict_seconds,
                            "train_rows": len(train), "validation_rows": len(validation),
                            "train_runs": train.run_id.nunique(), "validation_runs": validation.run_id.nunique(),
                            "transformed_feature_count": output_count, "linear_design_rank": rank,
                            "negative_predictions": int((prediction < 0).sum()),
                            "predicted_min_seconds": float(prediction.min()), "predicted_max_seconds": float(prediction.max()),
                            "fit_warnings": " | ".join(str(item.message) for item in caught)})
        table = validation[["run_id", "timestamp_seconds", "intersection_id", "approach_id"]].copy()
        table["model"], table["actual_future_wait_seconds"] = name, y_validation
        table["predicted_future_wait_seconds"] = prediction
        table["residual_actual_minus_predicted_seconds"] = y_validation - prediction
        prediction_tables.append(table)
        for run_id, part in table.groupby("run_id", sort=True):
            per_run.append({"model": name, "run_id": run_id, "rows": len(part), **metrics(part.actual_future_wait_seconds, part.predicted_future_wait_seconds)})
    return pd.DataFrame(comparisons), pd.concat(prediction_tables, ignore_index=True), pd.DataFrame(per_run), fitted_models


def make_plots(predictions, output_dir):
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / "work/matplotlib"))
    os.environ.setdefault("MPLBACKEND", "Agg")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    paths = []
    for name, part in predictions.groupby("model", sort=False):
        actual = part.actual_future_wait_seconds.to_numpy()
        predicted = part.predicted_future_wait_seconds.to_numpy()
        residual = actual - predicted
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.scatter(actual, predicted, s=10, alpha=0.3, color="#277b70")
        lower, upper = float(min(actual.min(), predicted.min())), float(max(actual.max(), predicted.max()))
        ax.plot([lower, upper], [lower, upper], "--", color="#ae5454", label="Ideal y = x")
        ax.set(title=f"{name}: validation only", xlabel="Actual future wait (s)", ylabel="Predicted future wait (s)")
        ax.legend()
        fig.tight_layout()
        path = output_dir / f"{name}_predicted_vs_actual.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        axes[0].scatter(predicted, residual, s=10, alpha=0.3, color="#657ca0")
        axes[0].axhline(0, linestyle="--", color="#ae5454")
        axes[0].set(title="Validation residuals", xlabel="Predicted future wait (s)", ylabel="Actual - predicted (s)")
        axes[1].hist(residual, bins=40, color="#c98b44")
        axes[1].set(title="Residual distribution", xlabel="Actual - predicted (s)", ylabel="Validation rows")
        fig.suptitle(name)
        fig.tight_layout()
        path = output_dir / f"{name}_residuals.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)
    return paths


def run_training(splits_dir=None, output_dir=None, findings_path=None, plots=True):
    splits_dir = Path(splits_dir or ROOT / "ml-service/data/splits")
    output_dir = Path(output_dir or ROOT / "artifacts/regression")
    frames, manifest, input_hashes = load_train_validation(splits_dir)
    comparison, predictions, per_run, models = evaluate_frames(**frames)
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(output_dir / "regression_comparison.csv", index=False, lineterminator="\n")
    predictions.to_csv(output_dir / "validation_predictions.csv", index=False, lineterminator="\n")
    per_run.to_csv(output_dir / "validation_per_run_metrics.csv", index=False, lineterminator="\n")
    paths = make_plots(predictions, output_dir) if plots else []
    for name, model in models.items():
        path = output_dir / f"{name}.joblib"
        joblib.dump(model, path)
        reloaded = joblib.load(path)
        expected = predictions.loc[predictions.model.eq(name), "predicted_future_wait_seconds"].to_numpy()
        np.testing.assert_allclose(reloaded.predict(prediction_frame(frames["validation"], TASK)), expected, rtol=1e-10, atol=1e-8)
    require(input_hashes == {name: digest(splits_dir / name) for name in input_hashes}, "train/validation inputs changed")
    summary = {
        "seed": 57, "syllabus_status": "UNVERIFIED", "experiment_status": "PROVISIONAL",
        "implemented_models": list(MODEL_NAMES), "other_models_added": [],
        "target": TARGET, "prediction_horizon_seconds": 60, "features": list(REGRESSION_FEATURES),
        "polynomial_scope": "10 numeric fields only; degree=2, include_bias=False; then StandardScaler; phase one-hot unexpanded",
        "fit_run_ids": sorted(frames["train"].run_id.unique().tolist()),
        "validation_run_ids": sorted(frames["validation"].run_id.unique().tolist()),
        "validation_prior_eda_exposure": manifest["prior_eda_exposure"]["validation"],
        "input_hashes_train_validation_only": input_hashes,
        "label_provenance": "manifest certifies exact same-run/intersection/approach source at t+60; unchanged audited CSV hashes checked",
        "test_data_opened": False, "test_scored": False, "hyperparameters_tuned": False,
        "negative_predictions_clipped": False, "artifact_reload_checks_passed": True,
        "plots": [path.name for path in paths], "fit_warnings": comparison.fit_warnings.tolist(),
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__},
        "training_script_sha256": digest(Path(__file__)),
        "syllabus_checklist_sha256": digest(ROOT / "docs/SYLLABUS_CHECKLIST.md"),
    }
    (output_dir / "experiment_manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if findings_path is not None:
        write_findings(Path(findings_path), comparison, per_run, summary, output_dir)
    return comparison, predictions, summary


def write_findings(path, comparison, per_run, summary, output_dir):
    text = """# Provisional regression findings

Official syllabus evidence has not been supplied. LinearRegression and degree-2
PolynomialFeatures + LinearRegression are **PROVISIONAL / UNVERIFIED**, explicitly named
by the user. No other regressors or complete-coverage/compliance claims are added.
The last-observed-wait reference is not a trained model.

## Objective and fit boundary

Predict the same virtual approach's mean queue-membership wait at exactly t+60 seconds
from the eleven approved current-time fields. Audited labels come from later simulation
states; they are not generated from current wait at training time. The persistence
reference predicts current mean_wait_seconds without a fitted parameter. Counts/queues/
waits are simulator truth, not GPS-only measurements. No real private GPS is used.

Fit on 8,712 rows from 18 runs; evaluate on 2,904 validation rows from six disjoint runs.
Only train.csv, validation.csv and the split manifest are opened for this experiment.
The manifest's future-label audit and unchanged input hashes are checked. test.csv is
never opened, hashed, transformed, predicted or scored. Test group IDs from the manifest
are read only to guard group overlap. No estimator or hyperparameter is selected/tuned
after seeing validation results. All current feature selection precedes preprocessing.

Numeric imputation, polynomial expansion, scaling and phase encoding are inside each
estimator pipeline and fit on train only. Polynomial expansion is limited to the ten
numeric inputs (65 outputs); phase one-hot columns are not multiplied. Total transformed
widths are 16 for linear and 71 for polynomial. StandardScaler follows imputation/expansion
on numeric fields only. Unknown phases do not change feature width. For later grouped
cross-validation, clone the entire unfitted model pipeline within each training fold.

## Validation comparison (raw predictions, seconds)

| Method | Status | MAE (s) | RMSE (s) | R2 | Fit seconds | Negative predictions |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
"""
    for row in comparison.to_dict("records"):
        r2 = "undefined" if pd.isna(row["validation_r2"]) else f"{row['validation_r2']:.6f}"
        text += f"| {row['model']} | {row['status']} | {row['validation_mae_seconds']:.4f} | {row['validation_rmse_seconds']:.4f} | {r2} | {row['training_seconds']:.6f} | {row['negative_predictions']} |\n"
    baseline = comparison.loc[comparison.model.eq("last_observed_wait")].iloc[0]
    text += "\n"
    for row in comparison.loc[comparison.model.ne("last_observed_wait")].to_dict("records"):
        delta = row["validation_mae_seconds"] - baseline.validation_mae_seconds
        text += f"- {row['model']}: validation MAE is {abs(delta):.4f}s {'lower' if delta < 0 else 'higher'} than persistence; no superiority on test or real traffic is established.\n"
    text += """
Fit time is one measured wall-clock fit including preprocessing, excluding loading,
prediction, plotting and serialization. Baseline fit time is zero (no training). Timing
varies by machine/load and is not a repeated performance benchmark. R2 is dimensionless;
negative R2 is possible and undefined constant-target per-run R2 is left blank. Metrics
are row-weighted over validation observations, not a confidence interval over independent
vehicles. Per-run results are saved separately.

## Diagnostics and limitations

- The two named models are unregularized least squares. Collinear simulator features and
  phase dummy columns can produce rank-deficient designs; rank/feature counts and any fit
  warnings are retained in the comparison CSV. No unrequested regularizer is introduced.
- Residuals are actual minus predicted: positive means underprediction. Both residual
  scatter/histogram and predicted-versus-actual plots are saved for all three methods.
  Raw predictions are not clipped or silently repaired; negative predictions are reported
  as nonphysical limitations, not fed to any controller.
- Current waiting is highly persistent by construction of this short-horizon point-queue
  simulator. High R2 can reflect that persistence and shared simulator assumptions, not
  robust real-world generalization or a causal signal-control benefit.
- Congestion classification labels elsewhere are feature-derived; these runs instead use
  future-state wait labels. No current congestion score or future outcome is a predictor.
- Validation is a development set: two of its runs were previously explored in EDA, as
  disclosed in LEAKAGE_AUDIT.md. The untouched final test remains reserved. No test
  performance, deployment readiness or official syllabus permission is claimed.
"""
    text += "\n### Per-run validation RMSE range\n\n"
    for name, part in per_run.groupby("model", sort=False):
        text += f"- {name}: {part.validation_rmse_seconds.min():.3f}Ã¢â‚¬â€œ{part.validation_rmse_seconds.max():.3f}s across six validation runs.\n"
    text += f"\nArtifacts: `{output_dir}` contains regression_comparison.csv, validation_predictions.csv, validation_per_run_metrics.csv, two full fitted pipelines, experiment_manifest.json and six diagnostic PNGs. Saved pipelines are reloaded and their validation predictions checked against the CSV. Raw input hashes remain unchanged.\n"
    text += "\nReproduce: `./ml-service/.venv/Scripts/python.exe ml-service/training/train_regression.py`. Seed 57 is retained; the two least-squares estimators themselves use no random fit.\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir", type=Path, default=ROOT / "ml-service/data/splits")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/regression")
    parser.add_argument("--findings-path", type=Path, default=ROOT / "docs/REGRESSION_FINDINGS.md")
    args = parser.parse_args()
    comparison, _, summary = run_training(args.splits_dir, args.output_dir, args.findings_path)
    print(comparison[["model", "status", "validation_mae_seconds", "validation_rmse_seconds", "validation_r2", "training_seconds", "negative_predictions"]].to_string(index=False))
    print("Test opened/scored:", summary["test_data_opened"], summary["test_scored"])
    print("Artifacts:", args.output_dir.resolve())
    print("Findings:", args.findings_path.resolve())


if __name__ == "__main__":
    main()
