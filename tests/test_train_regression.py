import builtins
import json
from pathlib import Path
import shutil

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import OneHotEncoder, PolynomialFeatures, StandardScaler

from training.prepare_data import REGRESSION_FEATURES
from training.train_regression import (
    MODEL_NAMES, ROOT, STATUS, build_regressor, evaluate_frames, load_train_validation,
    metrics, persistence_prediction, run_training,
)


def toy_frames():
    rng = np.random.default_rng(57)
    def frame(size, prefix):
        data = pd.DataFrame({name: rng.uniform(1,10,size) for name in REGRESSION_FEATURES if name != "current_phase"})
        data["current_phase"] = "ns_green" if prefix == "train" else "ew_green"
        data["run_id"] = prefix + "-run"
        data["timestamp_seconds"] = np.arange(size) * 10
        data["intersection_id"] = "unit-junction"
        data["approach_id"] = "north"
        data["congestion_level"] = "low"
        data["future_wait_seconds"] = 2 * data.mean_wait_seconds + data.incoming_vehicles + 5
        return data
    train, validation = frame(100,"train"), frame(12,"validation")
    train.loc[0,"mean_speed_kmh"] = np.nan
    validation.loc[0,"mean_speed_kmh"] = np.nan
    return train, validation


@pytest.mark.parametrize("name", ["random_forest", "ridge", "svm", "polynomial_degree3"])
def test_unrequested_or_unverified_extra_methods_are_not_silently_enabled(name):
    with pytest.raises(ValueError, match="Only provisional"):
        build_regressor(name)
    assert MODEL_NAMES == ("linear_regression", "polynomial_degree2")
    assert STATUS == "PROVISIONAL_UNVERIFIED"


@pytest.mark.parametrize("name", MODEL_NAMES)
def test_named_estimators_polynomial_degree_scope_and_unseen_categories(name):
    train, validation = toy_frames()
    pipeline = build_regressor(name)
    assert type(pipeline.named_steps["regressor"]) is LinearRegression
    pipeline.fit(train, train.future_wait_seconds)
    result = pipeline.predict(validation)
    assert np.isfinite(result).all()
    preprocessing = pipeline.named_steps["preprocessing"]
    numeric = preprocessing.named_steps["columns"].named_transformers_["numeric"]
    if name == "polynomial_degree2":
        polynomial = numeric.named_steps["polynomial"]
        assert polynomial.degree == 2 and polynomial.include_bias is False
        assert polynomial.n_features_in_ == 10 and polynomial.n_output_features_ == 65
        assert list(numeric.named_steps) == ["imputer", "polynomial", "scaler"]
    else:
        assert "polynomial" not in numeric.named_steps
    names = preprocessing.get_feature_names_out()
    assert not any("future_wait_seconds" in x or "congestion_level" in x or "run_id" in x for x in names)
    assert not any("^2" in x for x in names if x.startswith("categorical__"))
    frozen = joblib.hash(pipeline)
    changed = validation.copy()
    changed["future_wait_seconds"] = 99999
    changed["congestion_level"] = "ignored-label"
    changed = changed[list(reversed(changed.columns))]
    np.testing.assert_allclose(result, pipeline.predict(changed))
    assert joblib.hash(pipeline) == frozen


def test_all_transformers_and_estimators_fit_training_rows_and_future_target_only(monkeypatch):
    train, validation = toy_frames()
    calls = []
    for cls in (SimpleImputer, PolynomialFeatures, StandardScaler, OneHotEncoder, LinearRegression):
        original = cls.fit
        def wrapper(self, X, y=None, _original=original, _name=cls.__name__, **kwargs):
            calls.append((_name, len(X)))
            if _name == "LinearRegression":
                np.testing.assert_array_equal(y, train.future_wait_seconds.to_numpy())
                assert not np.array_equal(y, train.mean_wait_seconds.to_numpy())
            return _original(self, X, y, **kwargs)
        monkeypatch.setattr(cls, "fit", wrapper)
    comparison, predictions, _, _ = evaluate_frames(train, validation)
    assert {count for _, count in calls} == {100}
    assert sum(name == "PolynomialFeatures" for name, _ in calls) == 1
    assert sum(name == "LinearRegression" for name, _ in calls) == 2
    assert set(comparison.model) == {"last_observed_wait", *MODEL_NAMES}
    assert len(predictions) == 3 * len(validation)


def test_validation_outcomes_change_metrics_but_not_fitted_predictions():
    train, validation = toy_frames()
    comparison, original, _, _ = evaluate_frames(train, validation)
    changed = validation.copy()
    changed["future_wait_seconds"] += 1000
    altered, other, _, _ = evaluate_frames(train, changed)
    np.testing.assert_allclose(original.predicted_future_wait_seconds, other.predicted_future_wait_seconds, atol=1e-8)
    assert (altered.validation_mae_seconds > comparison.validation_mae_seconds).all()


def test_last_observed_wait_is_current_measurement_not_future_target():
    _, validation = toy_frames()
    before = validation.copy(deep=True)
    np.testing.assert_array_equal(persistence_prediction(validation), validation.mean_wait_seconds)
    assert not np.array_equal(persistence_prediction(validation), validation.future_wait_seconds)
    pd.testing.assert_frame_equal(validation,before)
    validation.loc[0,"mean_wait_seconds"] = np.nan
    with pytest.raises(AssertionError, match="baseline requires"):
        persistence_prediction(validation)


def test_metrics_have_correct_units_and_residual_sign_without_clipping():
    actual, prediction = np.array([2,4,6]), np.array([2,5,4])
    result = metrics(actual,prediction)
    assert result["validation_mae_seconds"] == 1
    assert result["validation_rmse_seconds"] == pytest.approx(np.sqrt(5/3))
    assert result["validation_r2"] == pytest.approx(.375)
    np.testing.assert_array_equal(actual-prediction,[0,-1,2])
    assert metrics([1,2,3],[-10,-10,-10])["validation_r2"] < 0
    assert metrics([1,1,1],[0,1,2])["validation_r2"] is None


@pytest.mark.parametrize("actual,prediction", [([],[]),([1],[np.nan]),([1,2],[1]),([np.inf],[0])])
def test_invalid_metrics_are_rejected(actual,prediction):
    with pytest.raises(AssertionError):
        metrics(actual,prediction)


def test_group_overlap_fails_before_training():
    train, validation = toy_frames()
    validation["run_id"] = train.run_id.iloc[0]
    with pytest.raises(AssertionError, match="overlap"):
        evaluate_frames(train,validation)


def copy_development_inputs(destination):
    destination.mkdir()
    # No test.csv is copied or read, even for creating the test fixture.
    for name in ("train.csv", "validation.csv", "split_manifest.json"):
        shutil.copyfile(ROOT / "ml-service/data/splits" / name, destination / name)
    return destination


@pytest.fixture(scope="module")
def experiment(tmp_path_factory):
    root = tmp_path_factory.mktemp("regression-development-only")
    inputs = copy_development_inputs(root / "splits-without-test")
    output = root / "outputs"
    comparison, predictions, summary = run_training(inputs, output, root / "findings.md")
    return inputs, output, comparison, predictions, summary


def test_experiment_works_without_test_file_and_metrics_match_saved_predictions(experiment):
    inputs, output, comparison, predictions, summary = experiment
    assert not (inputs / "test.csv").exists()
    assert summary["test_data_opened"] is summary["test_scored"] is False
    assert summary["syllabus_status"] == "UNVERIFIED"
    assert summary["other_models_added"] == []
    assert summary["prediction_horizon_seconds"] == 60
    assert set(summary["input_hashes_train_validation_only"]) == {"train.csv", "validation.csv", "split_manifest.json"}
    assert summary["negative_predictions_clipped"] is False
    assert summary["artifact_reload_checks_passed"]
    for name, part in predictions.groupby("model"):
        row = comparison.loc[comparison.model.eq(name)].iloc[0]
        expected = metrics(part.actual_future_wait_seconds,part.predicted_future_wait_seconds)
        for key,value in expected.items():
            assert row[key] == pytest.approx(value)
        assert row.negative_predictions == int(part.predicted_future_wait_seconds.lt(0).sum())
        np.testing.assert_allclose(part.residual_actual_minus_predicted_seconds,
                                   part.actual_future_wait_seconds-part.predicted_future_wait_seconds)
    assert len(pd.read_csv(output / "validation_per_run_metrics.csv")) == 18
    assert len(pd.read_csv(output / "regression_comparison.csv")) == 3
    assert len(summary["plots"]) == 6
    for name in summary["plots"]:
        assert (output / name).read_bytes().startswith(bytes.fromhex("89504e470d0a1a0a"))


def test_reload_pipelines_preserves_validation_predictions_and_training_only_scaler(experiment):
    inputs, output, _, predictions, _ = experiment
    validation = pd.read_csv(inputs / "validation.csv")
    for name in MODEL_NAMES:
        pipeline = joblib.load(output / f"{name}.joblib")
        expected = predictions.loc[predictions.model.eq(name),"predicted_future_wait_seconds"]
        np.testing.assert_allclose(pipeline.predict(validation),expected)
        numeric = pipeline.named_steps["preprocessing"].named_steps["columns"].named_transformers_["numeric"]
        assert numeric.named_steps["scaler"].n_samples_seen_ == 8712


def test_loader_never_opens_test_data_even_when_a_read_would_raise(monkeypatch):
    original = Path.open
    def guard(self,*args,**kwargs):
        if self.name == "test.csv":
            raise RuntimeError("test set opened")
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,"open",guard)
    original_builtin = builtins.open
    def builtin_guard(file,*args,**kwargs):
        if isinstance(file,(str,Path)) and Path(file).name == "test.csv":
            raise RuntimeError("test set opened")
        return original_builtin(file,*args,**kwargs)
    monkeypatch.setattr(builtins,"open",builtin_guard)
    frames, _, _ = load_train_validation(ROOT / "ml-service/data/splits")
    assert set(frames) == {"train","validation"}


@pytest.mark.parametrize("change", ["wrong-file", "missing-provenance", "wrong-horizon", "bad-hash"])
def test_loader_rejects_bad_contract_before_fit(tmp_path,change):
    inputs = copy_development_inputs(tmp_path / "inputs")
    path = inputs / "split_manifest.json"
    manifest = json.loads(path.read_text())
    if change == "wrong-file":
        manifest["splits"]["train"]["file"] = "test.csv"
    elif change == "missing-provenance":
        manifest["checks"]["future_labels_exact_same_group"] = False
    elif change == "wrong-horizon":
        manifest["prediction_horizon_seconds"] = 30
    else:
        manifest["splits"]["validation"]["sha256"] = "invalid"
    path.write_text(json.dumps(manifest),encoding="utf-8")
    with pytest.raises(AssertionError):
        load_train_validation(inputs)


def test_missing_audit_metadata_fails_before_any_model_fit(monkeypatch):
    train, validation = toy_frames()
    validation = validation.drop(columns=["timestamp_seconds"])
    def never_fit(*args, **kwargs):
        raise RuntimeError("unexpected early fit")
    monkeypatch.setattr(LinearRegression,"fit",never_fit)
    with pytest.raises(AssertionError, match="missing required"):
        evaluate_frames(train,validation)
