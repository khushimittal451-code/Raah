import builtins
import json
from pathlib import Path
import shutil

import joblib

import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

from training.preprocessing import prediction_frame
from training.train_classification import (
    LABELS, MODEL_NAMES, ROOT, SCALED_MODELS, STATUS, build_classifier, class_labels,
    classification_metrics, evaluate_frames, learned_state_hash, measure_latency,
    run_training, select_candidate,
)


def toy_frames():
    rng=np.random.default_rng(57)
    def frame(size,prefix):
        data=pd.DataFrame({"incoming_vehicles":rng.integers(0,10,size).astype(float),
                           "outgoing_vehicles":rng.integers(0,10,size).astype(float),
                           "seconds_in_phase":rng.uniform(0,30,size),"time_of_day":rng.uniform(0,24,size)})
        data["current_phase"]=[("ns_green","ns_yellow",None)[i%3] for i in range(size)] if prefix=="train" else "ew_green"
        data["congestion_level"]=[("low","medium","high")[i%3] for i in range(size)]
        data["run_id"]=prefix+"-run"
        data["timestamp_seconds"]=np.arange(size)*10
        data["intersection_id"]="unit-junction"
        data["approach_id"]="north"
        data["future_wait_seconds"]=999999
        data["mean_wait_seconds"]=999999
        return data
    train,validation=frame(90,"train"),frame(18,"validation")
    train.loc[0,"incoming_vehicles"]=np.nan
    validation.loc[0,"incoming_vehicles"]=np.nan
    return train,validation


@pytest.mark.parametrize("name",MODEL_NAMES)
def test_only_named_candidate_type_and_appropriate_scaling(name):
    expected={"LogisticRegression":LogisticRegression,"KNN":KNeighborsClassifier,"GaussianNB":GaussianNB,
              "SVC":SVC,"DecisionTreeClassifier":DecisionTreeClassifier,"RandomForestClassifier":RandomForestClassifier}
    pipeline=build_classifier(name)
    assert type(pipeline.named_steps["classifier"]) is expected[name]
    numeric=pipeline.named_steps["preprocessing"].named_steps["columns"].transformers[0][1]
    assert ("scaler" in numeric.named_steps)==(name in SCALED_MODELS)
    if name in {"LogisticRegression","SVC","DecisionTreeClassifier","RandomForestClassifier"}:
        assert pipeline.named_steps["classifier"].random_state==57
    assert STATUS=="PROVISIONAL_UNVERIFIED"


def test_extra_method_not_silently_enabled():
    with pytest.raises(ValueError):
        build_classifier("ExtraTreesClassifier")


def test_metrics_confusion_order_absent_classes_and_zero_denominators():
    scores,per_class,matrix=classification_metrics(["low","medium","high"],["low","low","high"])
    assert scores["accuracy"]==pytest.approx(2/3)
    assert scores["macro_f1"]==pytest.approx((2/3+0+1)/3)
    np.testing.assert_array_equal(matrix,[[1,0,0],[1,0,0],[0,0,1]])
    assert [item["class"] for item in per_class]==list(LABELS)
    assert per_class[1]["recall"]==0 and per_class[1]["precision"]==0 and per_class[1]["predicted_count"]==0
    single,_,_=classification_metrics(["low","low"],["low","low"])
    assert single["macro_f1"]==pytest.approx(1/3)
    assert single["macro_f1_present_labels"]==1
    hallucinated,_,_=classification_metrics(["low","low"],["high","low"])
    assert hallucinated["macro_f1_present_labels"]<1


@pytest.mark.parametrize("values",[[],[None],["UNKNOWN"],[["LOW"]]])
def test_bad_class_labels_rejected(values):
    with pytest.raises(AssertionError):
        class_labels(values)


def candidate_table():
    return pd.DataFrame({"model":MODEL_NAMES,"validation_macro_f1":[.70,.69,.60,.67,.65,.64],
                         "run_macro_f1_std":[.20,.05,.01,.02,.01,.03],"worst_run_macro_f1":[.3,.5,.5,.5,.5,.5]})


def test_selection_balances_f1_and_stability_with_predeclared_tolerance():
    table=candidate_table()
    selected=select_candidate(table)
    assert selected["candidate"]=="KNN"
    assert selected["eligible_candidates"]==["KNN","LogisticRegression"]
    assert selected["coverage_asserted"] is False
    assert select_candidate(table.iloc[::-1])==selected
    table.loc[table.model.eq("SVC"),"validation_macro_f1"] = .68
    assert "SVC" in select_candidate(table)["eligible_candidates"]


@pytest.mark.parametrize("column,value",[("validation_macro_f1",np.nan),("validation_macro_f1",2),("run_macro_f1_std",-1)])
def test_invalid_selection_statistics_fail(column,value):
    table=candidate_table()
    table.loc[0,column]=value
    with pytest.raises(AssertionError):
        select_candidate(table)


def test_every_fit_is_train_only_and_y_is_congestion_not_future_wait(monkeypatch):
    train,validation=toy_frames()
    calls=[]
    classes=(SimpleImputer,OneHotEncoder,StandardScaler,LogisticRegression,KNeighborsClassifier,
             GaussianNB,SVC,DecisionTreeClassifier,RandomForestClassifier)
    for cls in classes:
        original=cls.fit
        def wrapper(self,X,y=None,_original=original,_name=cls.__name__,**kwargs):
            calls.append((_name,len(X)))
            if _name in {"LogisticRegression","KNeighborsClassifier","GaussianNB","SVC","RandomForestClassifier"}:
                np.testing.assert_array_equal(y,train.congestion_level.str.upper())
            # Forest-internal DecisionTree fits receive bootstrap weights/encoded labels;
            # they still must see training row counts, never validation rows.
            return _original(self,X,y,**kwargs)
        monkeypatch.setattr(cls,"fit",wrapper)
    results=evaluate_frames(train,validation,batch_repeats=1,single_repeats=1)
    assert {count for _,count in calls}=={90}
    assert len(results["comparison"])==6
    assert set(results["predictions"].predicted_class)<=set(LABELS)
    assert set(results["class_counts"].split)=={"train","validation"}


@pytest.mark.parametrize("name",["KNN","RandomForestClassifier"])
def test_inference_state_guard_ignores_query_counters_but_detects_learned_mutations(name):
    train,validation=toy_frames()
    X=prediction_frame(train,"classification"); V=prediction_frame(validation,"classification")
    model=build_classifier(name).fit(X,class_labels(train.congestion_level))
    before=learned_state_hash(model)
    predicted=model.predict(V)
    timing=measure_latency(model,V,predicted,1,2)
    assert learned_state_hash(model)==before
    assert all(value>=0 for value in timing.values())
    estimator=model.named_steps["classifier"]
    if name=="KNN":
        estimator._fit_X[0,0]+=1
    else:
        estimator.estimators_[0].tree_.threshold[0]+=1
    assert learned_state_hash(model)!=before


def test_validation_labels_and_excluded_features_cannot_change_predictions():
    train,validation=toy_frames()
    model=build_classifier("LogisticRegression").fit(prediction_frame(train,"classification"),class_labels(train.congestion_level))
    expected=model.predict(validation)
    changed=validation.copy()
    changed["congestion_level"]="high"
    changed["future_wait_seconds"]=-99999
    changed["mean_wait_seconds"]=-99999
    changed=changed[list(reversed(changed.columns))]
    np.testing.assert_array_equal(expected,model.predict(changed))


def test_group_overlap_and_missing_training_class_fail_before_any_fit():
    train,validation=toy_frames()
    bad=validation.copy(); bad["run_id"]=train.run_id.iloc[0]
    with pytest.raises(AssertionError,match="overlap"):
        evaluate_frames(train,bad,1,1)
    train["congestion_level"]="low"
    with pytest.raises(AssertionError,match="training must contain"):
        evaluate_frames(train,validation,1,1)


@pytest.fixture(scope="module")
def experiment(tmp_path_factory):
    root=tmp_path_factory.mktemp("classification-no-test")
    inputs=root/"inputs"; inputs.mkdir()
    for name in ("train.csv","validation.csv","split_manifest.json"):
        shutil.copyfile(ROOT/"ml-service/data/splits"/name,inputs/name)
    output=root/"outputs"
    results,summary=run_training(inputs,output,root/"findings.md",batch_repeats=1,single_repeats=2)
    return inputs,output,results,summary


def test_real_experiment_works_without_test_file_and_exports_recomputed_metrics(experiment):
    inputs,output,results,summary=experiment
    assert not (inputs/"test.csv").exists()
    assert summary["test_data_opened"] is summary["test_scored"] is False
    assert summary["coverage_asserted"] is False and summary["syllabus_status"]=="UNVERIFIED"
    assert len(summary["methods"])==6 and summary["other_models_added"]==[]
    assert len(results["per_class"])==18 and len(results["per_run"])==36
    assert len(results["class_counts"])==6
    assert len(results["predictions"])==6*2904
    assert results["comparison"].selected_candidate.sum()==1
    for name,part in results["predictions"].groupby("model"):
        score,by_class,matrix=classification_metrics(part.actual_class,part.predicted_class)
        row=results["comparison"].set_index("model").loc[name]
        assert row.validation_accuracy==pytest.approx(score["accuracy"])
        assert row.validation_macro_f1==pytest.approx(score["macro_f1"])
        csv=pd.read_csv(output/f"{name}_confusion.csv",index_col=0)
        np.testing.assert_array_equal(csv.to_numpy(),matrix)
        assert matrix.sum()==2904 and list(csv.columns)==list(LABELS)
    assert len(summary["plots"])==6
    for path in summary["plots"]:
        assert (output/path).read_bytes().startswith(bytes.fromhex("89504e470d0a1a0a"))
    selected=joblib.load(output/"selected_classifier.joblib")
    validation=pd.read_csv(inputs/"validation.csv")
    expected=results["predictions"].loc[results["predictions"].model.eq(summary["selection"]["candidate"]),"predicted_class"]
    np.testing.assert_array_equal(selected.predict(validation),expected)


def test_loader_no_test_access_guard_remains_active(monkeypatch,tmp_path):
    original=Path.open
    def guard(self,*args,**kwargs):
        if self.name=="test.csv":
            raise RuntimeError("test file opened")
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,"open",guard)
    original_builtin=builtins.open
    def builtin_guard(file,*args,**kwargs):
        if isinstance(file,(str,Path)) and Path(file).name=="test.csv":
            raise RuntimeError("test file opened")
        return original_builtin(file,*args,**kwargs)
    monkeypatch.setattr(builtins,"open",builtin_guard)
    # Read the canonical source via the shared loader only, no test predictions.
    from training.train_regression import load_train_validation
    frames,_,_=load_train_validation(ROOT/"ml-service/data/splits")
    assert set(frames)=={"train","validation"}
