import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from app.schemas import LabeledTrafficRecord,TrafficObservation,congestion_level_for
from training import final_evaluation as final
from training.prepare_data import CLASSIFICATION_FEATURES,REGRESSION_FEATURES,digest
from training.train_classification import MODEL_NAMES,build_classifier


def fixture_inputs(tmp_path):
    splits=tmp_path/"splits"; splits.mkdir()
    frames={}
    for name in ("train","validation","test"):
        rows=[]
        for index in range(12):
            queue=(0,5,10)[index%3]
            observation=TrafficObservation(run_id="unit-"+name,timestamp_seconds=(index+1)*10,intersection_id="unit-junction",approach_id="north",
                mean_speed_kmh=50.0,free_flow_speed_kmh=60.0,vehicle_count=20,queue_length_vehicles=queue,
                mean_wait_seconds=float((0,20,60)[index%3]),incoming_vehicles=index%7,outgoing_vehicles=index%3,
                current_phase=("ns_green","ew_green","ns_yellow")[index%3],seconds_in_phase=float(index%5),
                time_of_day=(index+1)*10/3600,gps_sample_count=10)
            row=LabeledTrafficRecord(**observation.model_dump(),congestion_level=congestion_level_for(observation),future_wait_seconds=observation.mean_wait_seconds+3)
            rows.append(row.model_dump())
        frames[name]=pd.DataFrame(rows)
        frames[name].to_csv(splits/(name+".csv"),index=False,lineterminator="\n")
    manifest={"seed":57,"group_column":"run_id","prediction_horizon_seconds":60,
              "checks":{"future_labels_exact_same_group":True},
              "features":{"classification":list(CLASSIFICATION_FEATURES),"future_wait_regression":list(REGRESSION_FEATURES)},
              "splits":{name:{"file":name+".csv","sha256":digest(splits/(name+".csv")),"rows":12,"groups":1,"run_ids":["unit-"+name]} for name in frames},
              "prior_eda_exposure":{"validation":[]}}
    final.write_json(splits/"split_manifest.json",manifest)
    class_dir=tmp_path/"class_validation"; class_dir.mkdir()
    reg_dir=tmp_path/"reg_validation"; reg_dir.mkdir()
    classification=pd.DataFrame({"model":MODEL_NAMES,"evaluation_split":"validation", "validation_accuracy":[.6,.8,.5,.7,.7,.75],
        "validation_macro_f1":[.5,.7,.4,.6,.6,.65],"low_recall":.7,"medium_recall":[.1,.3,.1,.1,.1,.2],"high_recall":.7,"single_row_median_ms":2.0})
    regression=pd.DataFrame({"model":["last_observed_wait","linear_regression","polynomial_degree2"],"evaluation_split":"validation",
        "validation_mae_seconds":[10,7,6],"validation_rmse_seconds":[14,10,9],"validation_r2":[.8,.9,.95]})
    classification.to_csv(class_dir/"model_comparison.csv",index=False)
    regression.to_csv(reg_dir/"regression_comparison.csv",index=False)
    history={"input_hashes_train_validation_only":{"split_manifest.json":digest(splits/"split_manifest.json"),
        "train.csv":manifest["splits"]["train"]["sha256"],"validation.csv":manifest["splits"]["validation"]["sha256"]},"test_scored":False}
    final.write_json(class_dir/"experiment_manifest.json",{**history,"training_script_sha256":digest(final.ROOT/"ml-service/training/train_classification.py"),
        "model_parameters":{"KNN":build_classifier("KNN").named_steps["classifier"].get_params()}})
    final.write_json(reg_dir/"experiment_manifest.json",{**history,"training_script_sha256":digest(final.ROOT/"ml-service/training/train_regression.py")})
    return splits,class_dir,reg_dir,classification,regression


def freeze_fixture(tmp_path):
    splits,class_dir,reg_dir,_,_=fixture_inputs(tmp_path)
    output=tmp_path/"final"
    selection=final.freeze_selection(output,class_dir,reg_dir,splits)
    return splits,output,selection


def test_choice_uses_f1_then_recall_latency_and_regression_mae_rmse(tmp_path):
    _,_,_,classification,regression=fixture_inputs(tmp_path)
    chosen=final.choose_models(classification,regression)
    assert chosen["classification"]["model"]=="KNN"
    assert chosen["regression"]["model"]=="polynomial_degree2"
    classification.loc[classification.model.eq("RandomForestClassifier"),"validation_macro_f1"]=.7
    classification.loc[classification.model.eq("RandomForestClassifier"),"medium_recall"]=.4
    assert final.choose_models(classification,regression)["classification"]["model"]=="RandomForestClassifier"
    classification.loc[classification.model.eq("RandomForestClassifier"),"medium_recall"]=.3
    classification.loc[classification.model.eq("KNN"),"single_row_median_ms"]=1
    assert final.choose_models(classification,regression)["classification"]["model"]=="KNN"
    regression.loc[regression.model.eq("linear_regression"),"validation_mae_seconds"]=6
    regression.loc[regression.model.eq("linear_regression"),"validation_rmse_seconds"]=8
    assert final.choose_models(classification,regression)["regression"]["model"]=="linear_regression"


def test_freeze_never_opens_test_and_refuses_overwrite(tmp_path,monkeypatch):
    splits,class_dir,reg_dir,_,_=fixture_inputs(tmp_path)
    original=Path.open
    def guard(self,*args,**kwargs):
        if self==splits/"test.csv": raise RuntimeError("test opened before freeze")
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,"open",guard)
    output=tmp_path/"final"
    selection=final.freeze_selection(output,class_dir,reg_dir,splits)
    assert selection["test_data_opened_when_frozen"] is False
    assert (output/"selection_manifest.json").exists()
    with pytest.raises(AssertionError,match="already frozen"):
        final.freeze_selection(output,class_dir,reg_dir,splits)


def test_single_test_read_single_prediction_batches_and_safe_replay(tmp_path,monkeypatch):
    splits,output,selection=freeze_fixture(tmp_path)
    reads=[]
    original=Path.read_bytes
    def tracked(self):
        if self==splits/"test.csv":
            assert (output/"selection_manifest.json").is_file()
            assert (output/"test_access_claim.json").is_file()
            reads.append(str(self))
        return original(self)
    monkeypatch.setattr(Path,"read_bytes",tracked)
    result=final.evaluate_once(output,splits,plots=True)
    assert len(result["plots"])==3
    assert all((output/name).read_bytes().startswith(bytes.fromhex("89504e470d0a1a0a")) for name in result["plots"])
    assert len(reads)==1
    assert result["fit_rows"]==24 and result["fit_runs"]==2 and result["test_rows"]==12
    assert result["protocol"]["classification_predict_batches"]==result["protocol"]["regression_predict_batches"]==1
    assert final.evaluate_once(output,splits,plots=False)==result and len(reads)==1
    assert (output/"feature_schema.json").exists()
    schema=json.loads((output/"feature_schema.json").read_text())
    assert len(schema["tasks"]["classification"]["input_features"])==5
    for info in schema["tasks"].values():
        assert info["pipeline_sha256"]==digest(output/info["pipeline_file"])
        assert not any(item["name"] in {"run_id","congestion_level","future_wait_seconds"} for item in info["input_features"])
    classifier=joblib.load(output/"classification_pipeline.joblib")
    scaler=classifier.named_steps["preprocessing"].named_steps["columns"].named_transformers_["numeric"].named_steps["scaler"]
    assert scaler.n_samples_seen_==24
    claim=json.loads((output/"test_access_claim.json").read_text())
    assert claim["status"]=="COMPLETE"
    events=[json.loads(line) for line in (output/"test_usage_events.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events]==["SELECTION_FROZEN","REFIT_COMPLETE_BEFORE_TEST","TEST_OPEN_AUTHORIZED_AFTER_FROZEN_SELECTION","FINAL_TEST_COMPLETE"]


def test_refuses_mutated_frozen_manifest_before_test(tmp_path):
    splits,output,_=freeze_fixture(tmp_path)
    path=output/"selection_manifest.json"
    value=json.loads(path.read_text()); value["seed"]=99; final.write_json(path,value)
    with pytest.raises(AssertionError,match="frozen selection manifest changed"):
        final.evaluate_once(output,splits,plots=False)
    assert not (output/"test_access_claim.json").exists()


def test_postclaim_failure_cannot_reread_test(tmp_path):
    splits,output,_=freeze_fixture(tmp_path)
    with (splits/"test.csv").open("a",encoding="utf-8") as handle: handle.write("\n")
    with pytest.raises(AssertionError,match="test hash mismatch"):
        final.evaluate_once(output,splits,plots=False)
    assert json.loads((output/"test_access_claim.json").read_text())["status"]=="FAILED_AFTER_CLAIM_DO_NOT_RETRY"
    with pytest.raises(RuntimeError,match="already claimed"):
        final.evaluate_once(output,splits,plots=False)


def test_pretest_fit_failure_keeps_test_unconsumed_and_retry_safe(tmp_path,monkeypatch):
    splits,output,_=freeze_fixture(tmp_path)
    def fail(*args,**kwargs): raise ValueError("synthetic pre-test failure")
    with monkeypatch.context() as patch:
        patch.setattr(final,"refit_development",fail)
        with pytest.raises(ValueError,match="synthetic pre-test"):
            final.evaluate_once(output,splits,plots=False)
    assert not (output/"test_access_claim.json").exists()
    assert not (output/"evaluation_reservation.json").exists()
    assert final.evaluate_once(output,splits,plots=False)["protocol"]["test_csv_reads"]==1


def test_cached_metric_tampering_blocks_replay_not_new_evaluation(tmp_path):
    splits,output,_=freeze_fixture(tmp_path)
    final.evaluate_once(output,splits,plots=False)
    path=output/"metrics.json"; value=json.loads(path.read_text()); value["classification"]["accuracy"]=-123.0
    final.write_json(path,value)
    with pytest.raises(AssertionError,match="saved metrics hash mismatch"):
        final.evaluate_once(output,splits,plots=False)


def test_selection_rejects_nonvalidation_or_nonfinite_comparisons(tmp_path):
    _,_,_,classification,regression=fixture_inputs(tmp_path)
    classification.loc[0,"evaluation_split"]="test"
    with pytest.raises(AssertionError,match="validation results only"):
        final.choose_models(classification,regression)
    classification.loc[0,"evaluation_split"]="validation"; classification.loc[0,"validation_macro_f1"]=np.nan
    with pytest.raises(AssertionError,match="nonfinite"):
        final.choose_models(classification,regression)


def test_existing_reservation_blocks_concurrent_refit_without_deleting_owner_lock(tmp_path,monkeypatch):
    splits,output,_=freeze_fixture(tmp_path)
    path=output/"evaluation_reservation.json"
    final.write_json(path,{"owner":"another-evaluator"})
    original=path.read_bytes()
    def should_not_fit(*args,**kwargs): raise RuntimeError("concurrent refit")
    monkeypatch.setattr(final,"refit_development",should_not_fit)
    with pytest.raises(FileExistsError):
        final.evaluate_once(output,splits,plots=False)
    assert path.read_bytes()==original and not (output/"test_access_claim.json").exists()
