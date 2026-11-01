"""Freeze validation-only choices, then permit one final test reveal/prediction pass.

A persistent exclusive claim blocks repeat test reads. Subsequent complete calls return
saved metrics only. Failures after a claim require audit/recovery, never silent retesting.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sys
import time

import joblib
import numpy as np
import pandas as pd
import sklearn

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"ml-service"))
from app.schemas import LabeledTrafficRecord  # noqa: E402
from training.prepare_data import CLASSIFICATION_FEATURES,REGRESSION_FEATURES,digest,require  # noqa: E402
from training.preprocessing import prediction_frame  # noqa: E402
from training.train_classification import LABELS,MODEL_NAMES,build_classifier,class_labels,classification_metrics,learned_state_hash  # noqa: E402
from training.train_regression import MODEL_NAMES as REGRESSION_MODELS,build_regressor,load_train_validation,metrics as regression_metrics  # noqa: E402


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path,value,exclusive=False):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x" if exclusive else "w",encoding="utf-8",newline="\n") as handle:
        json.dump(value,handle,indent=2,sort_keys=True,allow_nan=False)
        handle.write("\n"); handle.flush(); os.fsync(handle.fileno())


def append_event(output,event,**data):
    with (Path(output)/"test_usage_events.jsonl").open("a",encoding="utf-8") as handle:
        handle.write(json.dumps({"event":event,"utc":now(),**data},sort_keys=True)+"\n")
        handle.flush(); os.fsync(handle.fileno())


def choose_models(classification,regression):
    require(set(classification.model)==set(MODEL_NAMES) and len(classification)==6,"need six saved classification candidates")
    require(classification.evaluation_split.eq("validation").all() and regression.evaluation_split.eq("validation").all(),"selection must use validation results only")
    cols=["validation_macro_f1","low_recall","medium_recall","high_recall","single_row_median_ms"]
    require(np.isfinite(classification[cols].to_numpy()).all(),"nonfinite classification comparison")
    require(classification.validation_macro_f1.between(0,1).all(),"invalid macro-F1")
    ranked=classification.copy()
    ranked["minimum_class_recall"]=ranked[["low_recall","medium_recall","high_recall"]].min(axis=1)
    ranked["mean_class_recall"]=ranked[["low_recall","medium_recall","high_recall"]].mean(axis=1)
    ranked=ranked.sort_values(["validation_macro_f1","minimum_class_recall","mean_class_recall","single_row_median_ms","model"],ascending=[False,False,False,True,True],kind="stable")
    eligible=regression[regression.model.isin(REGRESSION_MODELS)].copy()
    require(set(eligible.model)==set(REGRESSION_MODELS) and len(eligible)==2,"need the two named regression candidates")
    require(np.isfinite(eligible[["validation_mae_seconds","validation_rmse_seconds"]].to_numpy()).all(),"nonfinite regression comparison")
    require((eligible[["validation_mae_seconds","validation_rmse_seconds"]]>=0).all().all(),"negative regression error")
    selected_reg=eligible.sort_values(["validation_mae_seconds","validation_rmse_seconds","model"],kind="stable").iloc[0]
    selected_class=ranked.iloc[0]
    return {"classification":{"model":str(selected_class.model),"validation_macro_f1":float(selected_class.validation_macro_f1),
                              "minimum_class_recall":float(selected_class.minimum_class_recall),"mean_class_recall":float(selected_class.mean_class_recall),
                              "validation_accuracy":float(selected_class.validation_accuracy),"single_row_median_ms":float(selected_class.single_row_median_ms)},
            "regression":{"model":str(selected_reg.model),"validation_mae_seconds":float(selected_reg.validation_mae_seconds),
                          "validation_rmse_seconds":float(selected_reg.validation_rmse_seconds),"validation_r2":float(selected_reg.validation_r2)}}


def freeze_selection(output_dir=None,classification_dir=None,regression_dir=None,splits_dir=None):
    output=Path(output_dir or ROOT/"artifacts/final")
    output.mkdir(parents=True,exist_ok=True)
    path=output/"selection_manifest.json"
    require(not path.exists(),"selection is already frozen; refuse overwrite")
    classification_dir=Path(classification_dir or ROOT/"artifacts/classification")
    regression_dir=Path(regression_dir or ROOT/"artifacts/regression")
    splits=Path(splits_dir or ROOT/"ml-service/data/splits")
    class_file=classification_dir/"model_comparison.csv"; reg_file=regression_dir/"regression_comparison.csv"
    choices=choose_models(pd.read_csv(class_file),pd.read_csv(reg_file))
    split_manifest=json.loads((splits/"split_manifest.json").read_text(encoding="utf-8"))
    require(split_manifest["seed"]==57,"unexpected seed")
    require(tuple(split_manifest["features"]["classification"])==CLASSIFICATION_FEATURES and tuple(split_manifest["features"]["future_wait_regression"])==REGRESSION_FEATURES,"feature policy changed")
    class_history=json.loads((classification_dir/"experiment_manifest.json").read_text(encoding="utf-8"))
    reg_history=json.loads((regression_dir/"experiment_manifest.json").read_text(encoding="utf-8"))
    module_paths={"train_classification.py":ROOT/"ml-service/training/train_classification.py",
                  "train_regression.py":ROOT/"ml-service/training/train_regression.py",
                  "preprocessing.py":ROOT/"ml-service/training/preprocessing.py",
                  "prepare_data.py":ROOT/"ml-service/training/prepare_data.py"}
    require(class_history["training_script_sha256"]==digest(module_paths["train_classification.py"]),"classification validation source changed")
    require(reg_history["training_script_sha256"]==digest(module_paths["train_regression.py"]),"regression validation source changed")
    require(not class_history["test_scored"] and not reg_history["test_scored"],"history reports prior test model scoring")
    manifest_hash=digest(splits/"split_manifest.json")
    for history in (class_history,reg_history):
        require(history["input_hashes_train_validation_only"]["split_manifest.json"]==manifest_hash,"validation split manifest differs")
        for name in ("train","validation"):
            require(history["input_hashes_train_validation_only"][name+".csv"]==split_manifest["splits"][name]["sha256"],"saved validation input version mismatch")
    classifier=build_classifier(choices["classification"]["model"])
    regressor=build_regressor(choices["regression"]["model"])
    require(classifier.named_steps["classifier"].get_params()==class_history["model_parameters"][choices["classification"]["model"]],"classifier parameters changed since comparison")
    manifest={"schema_version":"final-selection-v1","created_utc":now(),"seed":57,"status":"PROVISIONAL_UNVERIFIED","coverage_asserted":False,
              "selection_rules":{"classification":"descending validation macro-F1; exact ties: higher minimum class recall, higher mean recall, lower saved single-row latency, then name; previous 0.02 stability band is not used",
                                 "regression":"ascending validation MAE, then RMSE, then name; persistence is a reference, not a fitted candidate"},
              "choices":choices,"refit_policy":"refit both complete selected pipelines from scratch on train+validation, including transforms; no test fitting",
              "test_protocol":"one read of test.csv after exclusive claim, one batch predict per selected model; all plots/metrics from cached predictions; no retuning",
              "feature_lists":{"classification":list(CLASSIFICATION_FEATURES),"regression":list(REGRESSION_FEATURES)},
              "classifier_parameters":classifier.named_steps["classifier"].get_params(),"regressor_parameters":regressor.named_steps["regressor"].get_params(),
              "preprocessing_policy":"same validated factories; median imputation; constant phase imputation/one-hot unknown ignore; numeric standard scaling; polynomial numeric degree2 only when selected",
              "split_manifest_sha256":manifest_hash,"split_spec":split_manifest["splits"],
              "evaluation_script_sha256":digest(Path(__file__)),"source_hashes":{name:digest(value) for name,value in module_paths.items()},
              "comparison_hashes":{"classification":digest(class_file),"regression":digest(reg_file)},
              "versions":{"python":platform.python_version(),"sklearn":sklearn.__version__,"numpy":np.__version__,"pandas":pd.__version__},
              "prior_test_history":"Earlier structural/schema/partition audits and preprocessing transforms accessed test without fitting or model scoring. Earlier supervised comparisons excluded test. Final score reveal happens in this workflow only.",
              "prior_eda_validation_exposure":split_manifest["prior_eda_exposure"]["validation"],"test_data_opened_when_frozen":False}
    write_json(path,manifest,exclusive=True)
    append_event(output,"SELECTION_FROZEN",selection_sha256=digest(path),classification=choices["classification"]["model"],regression=choices["regression"]["model"])
    return manifest


def check_frozen_contract(output,splits):
    path=output/"selection_manifest.json"
    require(path.is_file(),"freeze selection before evaluation")
    selection=json.loads(path.read_text(encoding="utf-8"))
    records=[json.loads(line) for line in (output/"test_usage_events.jsonl").read_text(encoding="utf-8").splitlines() if line]
    frozen=[record for record in records if record["event"]=="SELECTION_FROZEN"]
    require(len(frozen)==1 and frozen[0]["selection_sha256"]==digest(path),"frozen selection manifest changed")
    require(digest(Path(__file__))==selection["evaluation_script_sha256"],"evaluation protocol code changed after freeze")
    require(digest(splits/"split_manifest.json")==selection["split_manifest_sha256"],"split manifest changed after selection")
    for name,fingerprint in selection["source_hashes"].items():
        require(digest(ROOT/"ml-service/training"/name)==fingerprint,"model source changed after selection")
    require(selection["versions"]["sklearn"]==sklearn.__version__ and selection["versions"]["numpy"]==np.__version__,"library versions changed after selection")
    return selection,digest(path)


def refit_development(selection,splits,output):
    frames,split_manifest,_=load_train_validation(splits)
    development=pd.concat([frames["train"],frames["validation"]],ignore_index=True)
    require(not set(development.run_id)&set(selection["split_spec"]["test"]["run_ids"]),"refit overlaps test groups")
    classifier=build_classifier(selection["choices"]["classification"]["model"])
    regressor=build_regressor(selection["choices"]["regression"]["model"])
    require(classifier.named_steps["classifier"].get_params()==selection["classifier_parameters"],"frozen classifier parameters differ")
    require(regressor.named_steps["regressor"].get_params()==selection["regressor_parameters"],"frozen regressor parameters differ")
    start=time.perf_counter()
    classifier.fit(prediction_frame(development,"classification"),class_labels(development.congestion_level))
    class_seconds=time.perf_counter()-start
    start=time.perf_counter()
    regressor.fit(prediction_frame(development,"future_wait_regression"),development.future_wait_seconds.to_numpy(dtype=float))
    reg_seconds=time.perf_counter()-start
    schemas={}
    for task,model in (("classification",classifier),("regression",regressor)):
        path=output/(task+"_pipeline.joblib")
        joblib.dump(model,path)
        reloaded=joblib.load(path)
        frame=prediction_frame(development.head(5),"classification" if task=="classification" else "future_wait_regression")
        np.testing.assert_allclose(reloaded.predict(frame),model.predict(frame)) if task=="regression" else np.testing.assert_array_equal(reloaded.predict(frame),model.predict(frame))
        features=selection["feature_lists"][task]
        schemas[task]={"model":selection["choices"][task]["model"],"input_features":[{"name":name,"kind":"categorical" if name=="current_phase" else "numeric","column_required":True,"missing_cells_supported":True} for name in features],
                       "transformed_feature_order":model.named_steps["preprocessing"].get_feature_names_out().tolist(),
                       "pipeline_file":path.name,"pipeline_sha256":digest(path),"target":"congestion_level" if task=="classification" else "future_wait_seconds",
                       "target_units":"class LOW/MEDIUM/HIGH" if task=="classification" else "seconds, exact +60s mean queue wait"}
    schema={"version":"final-feature-schema-v1","status":"PROVISIONAL_UNVERIFIED","tasks":schemas,
            "fit_rows":len(development),"fit_run_ids":sorted(development.run_id.unique().tolist()),
            "excluded_features":"IDs, raw timestamp, targets, all future outcomes; classification also excludes defining rule inputs and count proxy",
            "missing_policy":"train+validation median; constant missing phase, unknown phase ignored; stricter traffic schemas still apply",
            "classification_label_order":list(LABELS),"refit_seconds":{"classification":class_seconds,"regression":reg_seconds}}
    write_json(output/"feature_schema.json",schema)
    # Use the exact persisted artifacts for final predictions.
    return joblib.load(output/"classification_pipeline.joblib"),joblib.load(output/"regression_pipeline.joblib"),schema


def save_test_plots(output,saved,matrix):
    """Render only cached final predictions; never call a model or reopen test data."""
    os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"work/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pd.DataFrame(matrix,index=pd.Index(LABELS,name="actual"),columns=LABELS).to_csv(output/"test_confusion_matrix.csv",lineterminator="\n")
    paths=[]
    fig,ax=plt.subplots(figsize=(6,5))
    image=ax.imshow(matrix,cmap="Blues",vmin=0)
    for row in range(3):
        for column in range(3):
            ax.text(column,row,str(int(matrix[row,column])),ha="center",va="center",color="black",
                    bbox={"facecolor":"white","edgecolor":"none","alpha":.9,"boxstyle":"round,pad=.15"})
    ax.set(xticks=range(3),yticks=range(3),xticklabels=LABELS,yticklabels=LABELS,
           xlabel="Predicted class",ylabel="Actual class",title="Selected classifier: FINAL TEST")
    fig.colorbar(image,ax=ax,label="Test rows"); fig.tight_layout()
    path=output/"test_classification_confusion.png"; fig.savefig(path,dpi=150,bbox_inches="tight"); plt.close(fig); paths.append(path.name)
    actual=saved.actual_future_wait_seconds.to_numpy(); predicted=saved.predicted_future_wait_seconds.to_numpy()
    residual=actual-predicted
    fig,ax=plt.subplots(figsize=(6,5))
    ax.scatter(actual,predicted,s=10,alpha=.3,color="#277b70")
    lower,upper=min(actual.min(),predicted.min()),max(actual.max(),predicted.max())
    ax.plot([lower,upper],[lower,upper],"--",color="#ae5454",label="Ideal y = x")
    ax.set(title="Selected regressor: FINAL TEST",xlabel="Actual future wait (s)",ylabel="Predicted future wait (s)"); ax.legend()
    fig.tight_layout(); path=output/"test_regression_predicted_vs_actual.png"; fig.savefig(path,dpi=150,bbox_inches="tight"); plt.close(fig); paths.append(path.name)
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    axes[0].scatter(predicted,residual,s=10,alpha=.3,color="#657ca0"); axes[0].axhline(0,linestyle="--",color="#ae5454")
    axes[0].set(title="Final test residuals",xlabel="Predicted future wait (s)",ylabel="Actual - predicted (s)")
    axes[1].hist(residual,bins=40,color="#c98b44"); axes[1].set(title="Final test residual distribution",xlabel="Actual - predicted (s)",ylabel="Test rows")
    fig.tight_layout(); path=output/"test_regression_residuals.png"; fig.savefig(path,dpi=150,bbox_inches="tight"); plt.close(fig); paths.append(path.name)
    return paths


def evaluate_once(output_dir=None,splits_dir=None,plots=True):
    output=Path(output_dir or ROOT/"artifacts/final"); splits=Path(splits_dir or ROOT/"ml-service/data/splits").resolve()
    selection,selection_hash=check_frozen_contract(output,splits)
    claim=output/"test_access_claim.json"
    if claim.exists():
        state=json.loads(claim.read_text(encoding="utf-8"))
        if state.get("status")=="COMPLETE":
            require(state["selection_sha256"]==selection_hash,"selection mismatch with completed evaluation")
            require(digest(output/"metrics.json")==state["metrics_sha256"],"saved metrics hash mismatch; refuse replay")
            return json.loads((output/"metrics.json").read_text(encoding="utf-8"))
        raise RuntimeError("test evaluation already claimed/incomplete; refuse reread or repredict; inspect audit and cached files")
    lock=output/"evaluation_reservation.json"
    write_json(lock,{"created_utc":now(),"selection_sha256":selection_hash},exclusive=True)
    claimed=False
    try:
        classifier,regressor,schema=refit_development(selection,splits,output)
        require(digest(output/"selection_manifest.json")==selection_hash,"selection changed during refit")
        append_event(output,"REFIT_COMPLETE_BEFORE_TEST",fit_rows=schema["fit_rows"],fit_runs=len(schema["fit_run_ids"]))
        spec=selection["split_spec"]["test"]
        require(spec["file"]=="test.csv","unexpected held-out file name")
        path=(splits/spec["file"]).resolve()
        require(path.parent==splits and path.name=="test.csv","test path escapes approved location")
        claim_state={"status":"CLAIMED_BEFORE_TEST_OPEN","created_utc":now(),"selection_sha256":selection_hash,
                     "evaluation_script_sha256":digest(Path(__file__)),"test_csv_reads":0,"classification_predict_batches":0,"regression_predict_batches":0}
        write_json(claim,claim_state,exclusive=True); claimed=True
        append_event(output,"TEST_OPEN_AUTHORIZED_AFTER_FROZEN_SELECTION",selection_sha256=selection_hash)
        raw=path.read_bytes()  # THE ONLY READ OF THE ACTUAL TEST DATA FILE.
        claim_state["test_csv_reads"]=1
        require(hashlib.sha256(raw).hexdigest()==spec["sha256"],"test hash mismatch; claim consumed, do not retry automatically")
        (output/"test_snapshot.csv").write_bytes(raw)  # Recovery evidence, not a new input for retries.
        test=pd.read_csv(io.BytesIO(raw))
        require(len(test)==spec["rows"] and test.run_id.nunique()==spec["groups"] and set(test.run_id)==set(spec["run_ids"]),"test membership/count mismatch")
        for record in test.to_dict("records"):
            if pd.isna(record["mean_speed_kmh"]): record["mean_speed_kmh"]=None
            LabeledTrafficRecord.model_validate(record)
        require(not set(test.run_id)&set(schema["fit_run_ids"]),"test/refit run overlap")
        class_state=learned_state_hash(classifier); reg_state=joblib.hash(regressor)
        claim_state["classification_predict_batches"]=1
        class_prediction=classifier.predict(prediction_frame(test,"classification"))
        # Cache class results immediately; never run this batch twice.
        np.save(output/"classification_test_predictions.npy",class_prediction,allow_pickle=False)
        claim_state["regression_predict_batches"]=1
        reg_prediction=regressor.predict(prediction_frame(test,"future_wait_regression"))
        np.save(output/"regression_test_predictions.npy",reg_prediction,allow_pickle=False)
        require(learned_state_hash(classifier)==class_state and joblib.hash(regressor)==reg_state,"test prediction changed learned model state")
        actual_class=class_labels(test.congestion_level); actual_wait=test.future_wait_seconds.to_numpy(dtype=float)
        class_metrics,per_class,matrix=classification_metrics(actual_class,class_prediction)
        reg=regression_metrics(actual_wait,reg_prediction)
        saved=test[["run_id","timestamp_seconds","intersection_id","approach_id"]].copy()
        saved["actual_class"],saved["predicted_class"]=actual_class,class_prediction
        saved["actual_future_wait_seconds"],saved["predicted_future_wait_seconds"]=actual_wait,reg_prediction
        saved["residual_actual_minus_predicted_seconds"]=actual_wait-reg_prediction
        saved.to_csv(output/"test_predictions.csv",index=False,lineterminator="\n")
        pd.DataFrame(per_class).to_csv(output/"test_per_class_metrics.csv",index=False,lineterminator="\n")
        run_metrics=[]
        for run_id,part in saved.groupby("run_id",sort=True):
            cm,_,_=classification_metrics(part.actual_class,part.predicted_class)
            rm=regression_metrics(part.actual_future_wait_seconds,part.predicted_future_wait_seconds)
            run_metrics.append({"run_id":run_id,"rows":len(part),"accuracy":cm["accuracy"],"macro_f1":cm["macro_f1"],
                                "mae_seconds":rm["validation_mae_seconds"],"rmse_seconds":rm["validation_rmse_seconds"]})
        pd.DataFrame(run_metrics).to_csv(output/"test_per_run_metrics.csv",index=False,lineterminator="\n")
        pd.DataFrame(matrix,index=pd.Index(LABELS,name="actual"),columns=LABELS).to_csv(output/"test_confusion_matrix.csv",lineterminator="\n")
        plot_paths=save_test_plots(output,saved,matrix) if plots else []
        final={"schema_version":"final-metrics-v1","evaluated_utc":now(),"selection_sha256":selection_hash,
               "evaluation_split":"test","status":"PROVISIONAL_UNVERIFIED","coverage_asserted":False,"seed":57,
               "fit_rows":schema["fit_rows"],"fit_runs":len(schema["fit_run_ids"]),"test_rows":len(test),"test_run_ids":sorted(test.run_id.unique().tolist()),
               "classification":{"model":selection["choices"]["classification"]["model"],"accuracy":class_metrics["accuracy"],"macro_f1":class_metrics["macro_f1"],
                                 "per_class":per_class,"confusion_matrix":matrix.tolist(),"label_order":list(LABELS),"orientation":"rows actual, columns predicted"},
               "regression":{"model":selection["choices"]["regression"]["model"],"mae_seconds":reg["validation_mae_seconds"],
                             "rmse_seconds":reg["validation_rmse_seconds"],"r2":reg["validation_r2"],"negative_predictions":int((reg_prediction<0).sum()),"predictions_clipped":False},
               "protocol":{"test_csv_reads":1,"classification_predict_batches":1,"regression_predict_batches":1,
                           "plots_and_per_run_metrics_use_cached_predictions":True,"refit_completed_before_test_open":True,
                           "selection_manifest_saved_before_test_open":True,"test_not_used_for_selection_or_refit":True},
               "plots":plot_paths,"pipeline_hashes":{task:info["pipeline_sha256"] for task,info in schema["tasks"].items()}}
        write_json(output/"metrics.json",final)
        claim_state.update(status="COMPLETE",completed_utc=now(),metrics_sha256=digest(output/"metrics.json"))
        write_json(claim,claim_state)
        append_event(output,"FINAL_TEST_COMPLETE",test_csv_reads=1,classification_predict_batches=1,regression_predict_batches=1,metrics_sha256=digest(output/"metrics.json"))
        return final
    except Exception as exc:
        append_event(output,"EVALUATION_FAILED",after_test_claim=claimed,error_type=type(exc).__name__,message=str(exc))
        if claimed:
            claim_state.update(status="FAILED_AFTER_CLAIM_DO_NOT_RETRY",error_type=type(exc).__name__,error=str(exc))
            write_json(claim,claim_state)
        raise
    finally:
        # Only an unconsumed pre-test reservation may be retried automatically.
        if not claimed and lock.is_file(): lock.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-only",action="store_true")
    parser.add_argument("--evaluate",action="store_true")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"artifacts/final")
    args=parser.parse_args()
    require(args.freeze_only != args.evaluate,"choose exactly one of --freeze-only or --evaluate")
    if args.freeze_only:
        value=freeze_selection(args.output_dir)
        print(json.dumps({"selection_manifest":str(args.output_dir/"selection_manifest.json"),"choices":value["choices"],"refit_policy":value["refit_policy"],"sha256":digest(args.output_dir/"selection_manifest.json")},indent=2))
    else:
        print(json.dumps(evaluate_once(args.output_dir),indent=2))


if __name__=="__main__":
    main()
