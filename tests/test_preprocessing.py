import json
from pathlib import Path
import shutil
import subprocess
import sys

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import NotFittedError
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from training.preprocessing import (
    MISSING_PHASE, ROOT, build_preprocessor, feature_names, fit_training_only,
    load_verified_splits, prediction_frame, run_preprocessing,
)


def sample_frames(task):
    numeric = [name for name in feature_names(task) if name != "current_phase"]
    train = pd.DataFrame({name: [1.0, np.nan, 3.0, 5.0] for name in numeric})
    validation = pd.DataFrame({name: [100.0, np.nan] for name in numeric})
    test = pd.DataFrame({name: [150.0, np.nan, 75.0] for name in numeric})
    train["current_phase"] = ["ns_green", "ns_yellow", None, "ns_green"]
    validation["current_phase"] = ["ew_green", None]
    test["current_phase"] = ["ew_yellow", "ns_green", pd.NA]
    for frame, prefix in ((train,"train"), (validation,"validation"), (test,"test")):
        frame["run_id"] = prefix + "-run"
        frame["congestion_level"] = "low"
        frame["future_wait_seconds"] = 999
        frame["scenario_type"] = "excluded-metadata"
    return train, validation, test


@pytest.mark.parametrize("task", ["classification", "future_wait_regression"])
@pytest.mark.parametrize("policy", ["standard", "none"])
def test_missing_values_unseen_categories_and_scaling_policy(task, policy):
    train, validation, test = sample_frames(task)
    before = [frame.copy(deep=True) for frame in (train, validation, test)]
    result = fit_training_only(train, validation, test, task=task, numeric_scaling=policy)
    columns = result.pipeline.named_steps["columns"]
    assert isinstance(columns, ColumnTransformer)
    numeric = columns.named_transformers_["numeric"]
    encoder = columns.named_transformers_["categorical"].named_steps["encoder"]
    assert "ew_green" not in encoder.categories_[0]
    assert MISSING_PHASE in encoder.categories_[0]
    numeric_count = len(feature_names(task)) - 1
    assert result.matrices["train"].shape[1] == numeric_count + 3
    np.testing.assert_allclose(numeric.named_steps["imputer"].statistics_, 3.0)
    if policy == "standard":
        np.testing.assert_allclose(numeric.named_steps["scaler"].mean_, 3.0)
        assert numeric.named_steps["scaler"].n_samples_seen_ == len(train)
        np.testing.assert_allclose(result.matrices["train"][:, 0], [-np.sqrt(2), 0, 0, np.sqrt(2)])
    else:
        assert "scaler" not in numeric.named_steps
        np.testing.assert_allclose(result.matrices["train"][:, 0], [1, 3, 3, 5])
    # One-hot columns are never centered/scaled; unknown category creates no new column.
    assert set(np.unique(result.matrices["train"][:, numeric_count:])) <= {0, 1}
    assert result.matrices["validation"][0, numeric_count:].sum() == 0
    assert result.matrices["validation"][1, numeric_count:].sum() == 1
    for name, frame in zip(("train", "validation", "test"), before):
        assert np.isfinite(result.matrices[name]).all()
    for frame, original in zip((train, validation, test), before):
        pd.testing.assert_frame_equal(frame, original)
    assert joblib.hash(result.pipeline) == result.fitted_state_hash


def test_each_learned_transform_fits_only_four_training_rows(monkeypatch):
    calls = []
    for cls in (SimpleImputer, OneHotEncoder, StandardScaler):
        original = cls.fit
        def wrapper(self, X, y=None, _original=original, _name=cls.__name__, **kwargs):
            calls.append((_name, len(X)))
            return _original(self, X, y, **kwargs)
        monkeypatch.setattr(cls, "fit", wrapper)
    train, validation, test = sample_frames("future_wait_regression")
    fit_training_only(train, validation, test, task="future_wait_regression", numeric_scaling="standard")
    assert sorted(calls) == sorted([("SimpleImputer",4), ("SimpleImputer",4), ("OneHotEncoder",4), ("StandardScaler",4)])


@pytest.mark.parametrize("missing", [np.nan, None, pd.NA])
def test_all_missing_training_numeric_column_is_retained_with_zero_fallback(missing):
    train, validation, test = sample_frames("future_wait_regression")
    train["mean_speed_kmh"] = missing
    result = fit_training_only(train, validation, test, task="future_wait_regression", numeric_scaling="standard")
    assert result.all_missing_training_numeric == ["mean_speed_kmh"]
    assert result.pipeline.named_steps["columns"].named_transformers_["numeric"].named_steps["imputer"].statistics_[0] == 0
    assert result.matrices["train"].shape[1] == result.matrices["validation"].shape[1]
    np.testing.assert_allclose(result.matrices["train"][:,0], 0)


def test_all_missing_training_phase_and_heldout_phase_do_not_change_categories():
    train, validation, test = sample_frames("classification")
    train["current_phase"] = pd.NA
    result = fit_training_only(train, validation, test, task="classification", numeric_scaling="none")
    encoder = result.pipeline.named_steps["columns"].named_transformers_["categorical"].named_steps["encoder"]
    assert encoder.categories_[0].tolist() == [MISSING_PHASE]
    assert result.matrices["validation"][0,-1] == 0
    assert result.matrices["validation"][1,-1] == 1


@pytest.mark.parametrize("task", ["classification", "future_wait_regression"])
def test_column_order_and_target_changes_cannot_change_transforms(task):
    train, validation, _ = sample_frames(task)
    pipeline = build_preprocessor(task, numeric_scaling="none")
    pipeline.fit(train)
    expected = pipeline.transform(validation)
    before_hash = joblib.hash(pipeline)
    changed = validation.copy(deep=True)
    changed["future_wait_seconds"] = -999999
    changed["congestion_level"] = "a-target-must-never-be-read"
    changed["run_id"] = "ignored-ID"
    changed["post_outcome_score"] = 12345
    changed = changed.loc[:, list(reversed(changed.columns))]
    np.testing.assert_array_equal(expected, pipeline.transform(changed))
    assert joblib.hash(pipeline) == before_hash
    assert list(pipeline.named_steps["select"].get_feature_names_out()) == list(feature_names(task))
    assert not any("future_wait_seconds" in name or "congestion_level" in name or "run_id" in name for name in pipeline.get_feature_names_out())


def test_factory_is_unfitted_cloneable_and_requires_explicit_scaling_choice():
    train, _, _ = sample_frames("classification")
    pipeline = build_preprocessor("classification", numeric_scaling="standard")
    with pytest.raises(NotFittedError):
        pipeline.transform(train)
    pipeline.fit(train)
    with pytest.raises(NotFittedError):
        clone(pipeline).transform(train)
    with pytest.raises(TypeError):
        build_preprocessor("classification")
    with pytest.raises(ValueError):
        build_preprocessor("unknown", numeric_scaling="standard")
    with pytest.raises(ValueError):
        build_preprocessor("classification", numeric_scaling="automatic")


@pytest.mark.parametrize("kind", ["missing-column", "duplicate-column", "unnamed-array", "infinite", "boolean", "invalid-category"])
def test_invalid_prediction_inputs_fail_early(kind):
    train, _, _ = sample_frames("classification")
    if kind == "missing-column":
        train = train.drop(columns=["incoming_vehicles"])
    elif kind == "duplicate-column":
        train = pd.concat([train, train[["incoming_vehicles"]]], axis=1)
    elif kind == "unnamed-array":
        train = train.to_numpy()
    elif kind == "infinite":
        train.loc[0,"incoming_vehicles"] = np.inf
    elif kind == "boolean":
        train["incoming_vehicles"] = True
    else:
        train["current_phase"] = [1,2,3,4]
    with pytest.raises((ValueError, TypeError)):
        prediction_frame(train, "classification")


def test_run_overlap_rejected_before_fit(monkeypatch):
    train, validation, test = sample_frames("classification")
    validation["run_id"] = train.run_id.iloc[0]
    def never_fit(*args, **kwargs):
        raise RuntimeError("fit was called before group guard")
    monkeypatch.setattr(SimpleImputer, "fit", never_fit)
    with pytest.raises(AssertionError, match="overlap"):
        fit_training_only(train, validation, test, task="classification", numeric_scaling="none")


def test_manifest_integrity_failure_is_rejected_before_fitting(tmp_path):
    source = ROOT / "ml-service/data/splits"
    for path in source.iterdir():
        if path.is_file():
            shutil.copyfile(path, tmp_path / path.name)
    with (tmp_path / "validation.csv").open("a", encoding="utf-8") as handle:
        handle.write("\n")
    with pytest.raises(AssertionError, match="hash mismatch"):
        load_verified_splits(tmp_path)


def test_real_splits_fit_only_manifest_train_groups_and_save_reloadable_pipeline(tmp_path):
    report = run_preprocessing("future_wait_regression", "standard", output_dir=tmp_path)
    assert report["fit_rows"] == report["scaler_training_rows"] == 8712
    assert report["shapes"] == {"train":[8712,16], "validation":[2904,16], "test":[2904,16]}
    assert all(report["checks"].values())
    manifest = json.loads((ROOT / "ml-service/data/splits/split_manifest.json").read_text())
    assert report["fit_run_ids"] == manifest["splits"]["train"]["run_ids"]
    loaded = joblib.load(tmp_path / report["artifact"])
    frames, _ = load_verified_splits(ROOT / "ml-service/data/splits")
    assert loaded.transform(frames["test"].head(3)).shape == (3,16)


def test_cli_artifact_can_load_in_a_fresh_python_process(tmp_path):
    result = subprocess.run([sys.executable, str(ROOT / "ml-service/training/preprocessing.py"),
                             "--task", "classification", "--numeric-scaling", "none", "--output-dir", str(tmp_path)],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    program = "import sys; sys.path.insert(0,'ml-service'); import joblib; p=joblib.load(sys.argv[1]); print(type(p.named_steps['select']).__module__)"
    loaded = subprocess.run([sys.executable, "-c", program, str(tmp_path / "classification-none.joblib")],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert loaded.returncode == 0, loaded.stderr
    assert loaded.stdout.strip() == "training.preprocessing"
