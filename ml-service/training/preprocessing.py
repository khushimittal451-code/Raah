"""Train-only sklearn preprocessing for the approved prediction-time feature lists.

Factories return unfitted pipelines. Use run_preprocessing for manifest-verified splits.
No estimator, target encoding, model comparison or test-set optimization is performed.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml-service"))
from training.prepare_data import (  # noqa: E402
    CLASSIFICATION_FEATURES, REGRESSION_FEATURES, audit_feature_lists, digest, require,
)

TASK_FEATURES = {"classification": CLASSIFICATION_FEATURES, "future_wait_regression": REGRESSION_FEATURES}
CATEGORICAL_FEATURES = ("current_phase",)
MISSING_PHASE = "__MISSING_PHASE__"


def feature_names(task):
    if task not in TASK_FEATURES:
        raise ValueError(f"unknown task: {task}")
    audit_feature_lists()
    return tuple(TASK_FEATURES[task])


def prediction_frame(frame, task):
    """Stateless selection/normalization; no statistics are learned or data mutated."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("use a named pandas DataFrame, not an ambiguous positional array")
    if frame.columns.duplicated().any():
        raise ValueError("duplicate input column names")
    names = feature_names(task)
    missing = set(names) - set(frame.columns)
    if missing:
        raise ValueError(f"missing required feature columns: {sorted(missing)}")
    selected = frame.loc[:, list(names)].copy(deep=True)
    for name in names:
        values = selected[name]
        if name in CATEGORICAL_FEATURES:
            if any(not isinstance(value, str) for value in values.dropna()):
                raise ValueError(f"categorical values must be strings or missing: {name}")
            selected[name] = values.astype(object).where(values.notna(), np.nan)
        else:
            if any(isinstance(value, (bool, np.bool_)) for value in values.dropna()):
                raise ValueError(f"boolean is not a numeric measurement: {name}")
            numbers = pd.to_numeric(values, errors="raise").to_numpy(dtype=float, na_value=np.nan)
            if np.isinf(numbers).any():
                raise ValueError(f"infinite measurement: {name}")
            selected[name] = numbers
    return selected


class PredictionFeatureSelector(TransformerMixin, BaseEstimator):
    """Force canonical feature order and exclude identifiers/targets/unknown extras."""

    def __init__(self, task):
        self.task = task

    def fit(self, X, y=None):
        frame = prediction_frame(X, self.task)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.n_features_in_ = frame.shape[1]
        return self

    def transform(self, X):
        check_is_fitted(self, "feature_names_in_")
        return prediction_frame(X, self.task)

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, "feature_names_in_")
        return self.feature_names_in_.copy()


def build_preprocessor(task, *, numeric_scaling):
    """Return UNFITTED selector + ColumnTransformer Pipeline.

    numeric_scaling='standard': use for scale-sensitive linear/distance/SVM workflows.
    numeric_scaling='none': use for decision-tree/random-forest style workflows.
    The caller must choose explicitly; this factory does not decide model permission.
    """
    names = feature_names(task)
    if numeric_scaling not in {"standard", "none"}:
        raise ValueError("numeric_scaling must be 'standard' or 'none'")
    numeric = [name for name in names if name not in CATEGORICAL_FEATURES]
    categorical = [name for name in names if name in CATEGORICAL_FEATURES]
    steps = [("imputer", SimpleImputer(strategy="median", keep_empty_features=True))]
    if numeric_scaling == "standard":
        steps.append(("scaler", StandardScaler()))
    columns = ColumnTransformer(
        transformers=[
            ("numeric", Pipeline(steps), numeric),
            ("categorical", Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value=MISSING_PHASE, keep_empty_features=True)),
                ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ]), categorical),
        ],
        remainder="drop", sparse_threshold=0, verbose_feature_names_out=True,
    )
    return Pipeline([("select", PredictionFeatureSelector(task)), ("columns", columns)])


@dataclass
class TransformedSplits:
    pipeline: Pipeline
    matrices: dict[str, np.ndarray]
    output_feature_names: list[str]
    training_run_ids: list[str]
    all_missing_training_numeric: list[str]
    fitted_state_hash: str


def fit_training_only(train, validation, test, *, task, numeric_scaling):
    """Fit ONCE on the designated training frame; other sets are transform-only.

    Group guards catch overlap. For manifest-verified train identities and input integrity,
    prefer run_preprocessing, which additionally checks split_manifest.json and hashes.
    """
    frames = {"train": train, "validation": validation, "test": test}
    groups = {}
    for name, frame in frames.items():
        require(isinstance(frame, pd.DataFrame) and len(frame) > 0, f"empty/non-DataFrame split: {name}")
        require("run_id" in frame and frame.run_id.notna().all(), f"run IDs required for fit boundary: {name}")
        groups[name] = set(frame.run_id)
        prediction_frame(frame, task)  # Validation only: no learned transform or target access.
    require(not (groups["train"] & groups["validation"] or groups["train"] & groups["test"] or groups["validation"] & groups["test"]), "run group overlap before preprocessing")
    pipeline = build_preprocessor(task, numeric_scaling=numeric_scaling)
    matrices = {"train": pipeline.fit_transform(train)}
    fitted_state = joblib.hash(pipeline)
    for name in ("validation", "test"):
        matrices[name] = pipeline.transform(frames[name])
        require(joblib.hash(pipeline) == fitted_state, f"fitted state changed while transforming {name}")
    output_names = [str(name) for name in pipeline.get_feature_names_out()]
    for name, matrix in matrices.items():
        require(matrix.shape == (len(frames[name]), len(output_names)), f"unstable feature width/order: {name}")
        require(np.isfinite(matrix).all(), f"nonfinite transformed matrix: {name}")
    canonical_train = prediction_frame(train, task)
    all_missing = [name for name in canonical_train if name not in CATEGORICAL_FEATURES and canonical_train[name].isna().all()]
    return TransformedSplits(pipeline, matrices, output_names, sorted(groups["train"]), all_missing, fitted_state)


def load_verified_splits(splits_dir):
    splits_dir = Path(splits_dir)
    manifest = json.loads((splits_dir / "split_manifest.json").read_text(encoding="utf-8"))
    require(manifest["seed"] == 57 and manifest["group_column"] == "run_id", "unexpected split policy")
    require(tuple(manifest["features"]["classification"]) == CLASSIFICATION_FEATURES and
            tuple(manifest["features"]["future_wait_regression"]) == REGRESSION_FEATURES,
            "manifest feature policy differs from current approved lists")
    frames = {}
    for name in ("train", "validation", "test"):
        info = manifest["splits"][name]
        path = (splits_dir / info["file"]).resolve()
        require(path.parent == splits_dir.resolve(), "split path must stay in split directory")
        require(digest(path) == info["sha256"], f"split hash mismatch: {name}; rerun audited preparation if needed")
        frame = pd.read_csv(path)
        require(len(frame) == info["rows"] and set(frame.run_id) == set(info["run_ids"]), f"manifest membership/count mismatch: {name}")
        require(len(set(frame.run_id)) == info["groups"], f"manifest group count mismatch: {name}")
        frames[name] = frame
    return frames, manifest


def run_preprocessing(task, numeric_scaling, splits_dir=None, output_dir=None):
    splits_dir = Path(splits_dir or ROOT / "ml-service/data/splits")
    output_dir = Path(output_dir or ROOT / "artifacts/preprocessing")
    before = {p.name: digest(p) for p in splits_dir.glob("*") if p.is_file()}
    frames, manifest = load_verified_splits(splits_dir)
    result = fit_training_only(**frames, task=task, numeric_scaling=numeric_scaling)
    require(set(result.training_run_ids) == set(manifest["splits"]["train"]["run_ids"]), "fit groups differ from manifest train groups")
    require(before == {p.name: digest(p) for p in splits_dir.glob("*") if p.is_file()}, "raw splits or manifest changed")
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{task}-{numeric_scaling}"
    artifact = output_dir / f"{stem}.joblib"
    joblib.dump(result.pipeline, artifact)
    columns = result.pipeline.named_steps["columns"]
    numeric = columns.named_transformers_["numeric"]
    report = {
        "task": task, "numeric_scaling": numeric_scaling, "seed": 57,
        "input_features": list(feature_names(task)), "output_feature_names": result.output_feature_names,
        "shapes": {name: list(values.shape) for name, values in result.matrices.items()},
        "fit_run_ids": result.training_run_ids, "fit_split": "train", "fit_rows": len(frames["train"]),
        "numeric_imputer": "training median; all-missing training column fallback=0 with column retained",
        "all_missing_training_numeric_columns": result.all_missing_training_numeric,
        "categorical_imputer": "constant __MISSING_PHASE__", "unknown_category_policy": "ignore, all-zero categorical block; no new columns",
        "training_categories": [[str(value) for value in array] for array in columns.named_transformers_["categorical"].named_steps["encoder"].categories_],
        "numeric_training_statistics": numeric.named_steps["imputer"].statistics_.tolist(),
        "scaler_training_rows": int(numeric.named_steps["scaler"].n_samples_seen_) if "scaler" in numeric.named_steps else None,
        "checks": {"fit_training_groups_only": True, "heldout_transform_only": True,
                   "fitted_state_unchanged_on_heldout": True, "all_matrices_finite": True,
                   "canonical_column_order": True, "raw_split_files_unchanged": True},
        "fitted_state_hash": result.fitted_state_hash, "artifact": artifact.name,
        "scope": "preprocessing only; no model/target fit, evaluation, or syllabus compliance claim",
    }
    (output_dir / f"{stem}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=[*TASK_FEATURES, "all"], default="all")
    parser.add_argument("--numeric-scaling", choices=["standard", "none", "both"], default="both")
    parser.add_argument("--splits-dir", type=Path, default=ROOT / "ml-service/data/splits")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/preprocessing")
    args = parser.parse_args()
    tasks = list(TASK_FEATURES) if args.task == "all" else [args.task]
    policies = ["standard", "none"] if args.numeric_scaling == "both" else [args.numeric_scaling]
    reports = [run_preprocessing(task, policy, args.splits_dir, args.output_dir) for task in tasks for policy in policies]
    print(json.dumps([{key: report[key] for key in ("task", "numeric_scaling", "shapes", "fit_rows", "scaler_training_rows", "checks", "artifact")}
                      for report in reports], indent=2))


if __name__ == "__main__":
    # Use the importable module identity so joblib artifacts load in another process.
    from training.preprocessing import main as canonical_main
    canonical_main()
