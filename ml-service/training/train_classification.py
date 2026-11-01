"""Six explicit provisional classifiers; fixed train groups, validation only, no test.

Selection rule is fixed before training: within 0.02 of best validation macro-F1,
prefer lowest per-run F1 standard deviation, then highest worst-run F1/global F1/name.
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
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml-service"))
from training.prepare_data import CLASSIFICATION_FEATURES, digest, require  # noqa: E402
from training.preprocessing import build_preprocessor, prediction_frame  # noqa: E402
from training.train_regression import load_train_validation  # noqa: E402

LABELS = ("LOW", "MEDIUM", "HIGH")
MODEL_NAMES = ("LogisticRegression", "KNN", "GaussianNB", "SVC", "DecisionTreeClassifier", "RandomForestClassifier")
SCALED_MODELS = {"LogisticRegression", "KNN", "SVC"}
STATUS = "PROVISIONAL_UNVERIFIED"
F1_TOLERANCE = 0.02
SELECTION_RULE = "global macro-F1 >= best-0.02; minimize per-run present-label macro-F1 population std; then maximize worst-run F1, global F1; name breaks exact ties"


def build_classifier(name):
    if name not in MODEL_NAMES:
        raise ValueError("only the six explicitly named provisional classifiers are enabled")
    estimators = {
        "LogisticRegression": lambda: LogisticRegression(C=1.0, max_iter=2000, solver="lbfgs", random_state=57),
        "KNN": lambda: KNeighborsClassifier(n_neighbors=15, weights="distance", p=2, n_jobs=1),
        "GaussianNB": lambda: GaussianNB(var_smoothing=1e-9),
        "SVC": lambda: SVC(C=1.0, kernel="rbf", gamma="scale", random_state=57),
        "DecisionTreeClassifier": lambda: DecisionTreeClassifier(max_depth=8, min_samples_leaf=20, random_state=57),
        "RandomForestClassifier": lambda: RandomForestClassifier(n_estimators=200, max_depth=12, min_samples_leaf=5, max_features="sqrt", n_jobs=1, random_state=57),
    }
    return Pipeline([
        ("preprocessing", build_preprocessor("classification", numeric_scaling="standard" if name in SCALED_MODELS else "none")),
        ("classifier", estimators[name]()),
    ])


def class_labels(values):
    values = np.asarray(values)
    require(values.ndim == 1 and len(values) > 0 and not pd.isna(values).any(), "empty/missing or non-vector class labels")
    labels = np.asarray([str(value).upper() for value in values])
    require(set(labels) <= set(LABELS), "unknown congestion class")
    return labels


def classification_metrics(actual, predicted):
    actual, predicted = class_labels(actual), class_labels(predicted)
    require(actual.shape == predicted.shape, "class prediction shape mismatch")
    precision, recall, f1, support = precision_recall_fscore_support(actual, predicted, labels=list(LABELS), zero_division=0)
    matrix = confusion_matrix(actual, predicted, labels=list(LABELS))
    per_class = [{"class": name, "precision": float(precision[index]), "recall": float(recall[index]),
                  "f1": float(f1[index]), "support": int(support[index]),
                  "predicted_count": int((predicted == name).sum())} for index, name in enumerate(LABELS)]
    present = [name for name in LABELS if name in set(actual) | set(predicted)]
    return {"accuracy": float(accuracy_score(actual, predicted)),
            "macro_f1": float(f1_score(actual, predicted, labels=list(LABELS), average="macro", zero_division=0)),
            "macro_f1_present_labels": float(f1_score(actual, predicted, labels=present, average="macro", zero_division=0)),
            "actual_classes_present": ",".join(name for name in LABELS if name in set(actual))}, per_class, matrix


def learned_state_hash(model):
    """Hash all learned state, normalizing only KNN's runtime query counters."""
    estimator = model.named_steps["classifier"]
    state = dict(estimator.__dict__)
    if isinstance(estimator, KNeighborsClassifier) and state.get("_tree") is not None:
        # get_arrays includes learned data, indices, tree nodes and bounds. The
        # pickled tree also contains query statistics that legitimately change.
        state["_tree"] = estimator._tree.get_arrays()
    return joblib.hash({"preprocessing": model.named_steps["preprocessing"], "classifier": state})


def measure_latency(model, features, expected, batch_repeats=5, single_repeats=20):
    require(type(batch_repeats) is int and type(single_repeats) is int and batch_repeats >= 1 and single_repeats >= 1, "latency repeat counts must be positive integers")
    np.testing.assert_array_equal(model.predict(features), expected)  # Warmup, excluded from timings.
    batches, singles = [], []
    for _ in range(batch_repeats):
        start = time.perf_counter()
        prediction = model.predict(features)
        batches.append(time.perf_counter() - start)
        np.testing.assert_array_equal(prediction, expected)
    for index in range(single_repeats):
        row = features.iloc[[index % len(features)]]
        start = time.perf_counter()
        prediction = model.predict(row)
        singles.append(time.perf_counter() - start)
        np.testing.assert_array_equal(prediction, expected[[index % len(features)]])
    return {"inference_batch_median_ms": float(np.median(batches) * 1000),
            "inference_batch_p95_ms": float(np.quantile(batches, .95) * 1000),
            "inference_amortized_us_per_row": float(np.median(batches) * 1e6 / len(features)),
            "single_row_median_ms": float(np.median(singles) * 1000)}


def select_candidate(comparison):
    require(set(comparison.model) == set(MODEL_NAMES) and len(comparison) == 6, "selection requires all six candidates")
    require(np.isfinite(comparison[["validation_macro_f1", "run_macro_f1_std", "worst_run_macro_f1"]].to_numpy()).all(), "invalid candidate scores")
    require(comparison.validation_macro_f1.between(0,1).all() and comparison.worst_run_macro_f1.between(0,1).all() and comparison.run_macro_f1_std.ge(0).all(), "candidate metrics outside valid ranges")
    best = float(comparison.validation_macro_f1.max())
    eligible = comparison[comparison.validation_macro_f1 >= best - F1_TOLERANCE - 1e-12]
    ranked = eligible.sort_values(["run_macro_f1_std", "worst_run_macro_f1", "validation_macro_f1", "model"],
                                  ascending=[True, False, False, True], kind="stable")
    return {"candidate": str(ranked.iloc[0].model), "status": STATUS, "coverage_asserted": False,
            "selection_rule": SELECTION_RULE, "macro_f1_tolerance": F1_TOLERANCE,
            "best_global_macro_f1": best, "eligible_candidates": sorted(eligible.model.tolist()),
            "selected_global_macro_f1": float(ranked.iloc[0].validation_macro_f1),
            "selected_run_macro_f1_std": float(ranked.iloc[0].run_macro_f1_std),
            "scope": "validation-selected candidate for further review only; not deployed or independently test-validated"}


def evaluate_frames(train, validation, batch_repeats=5, single_repeats=20):
    required = set(CLASSIFICATION_FEATURES) | {"run_id", "timestamp_seconds", "intersection_id", "approach_id", "congestion_level"}
    for name, frame in (("train", train), ("validation", validation)):
        require(isinstance(frame, pd.DataFrame) and len(frame) > 0 and required <= set(frame.columns), f"missing required {name} data")
    require(not set(train.run_id) & set(validation.run_id), "train/validation run overlap")
    require(len(train) >= 15, "KNN fixed n_neighbors=15 requires at least 15 training rows")
    X_train, X_validation = prediction_frame(train,"classification"), prediction_frame(validation,"classification")
    y_train, y_validation = class_labels(train.congestion_level), class_labels(validation.congestion_level)
    require(set(y_train) == set(LABELS), "training must contain LOW, MEDIUM and HIGH")
    majority_class = sorted(LABELS, key=lambda name: (-int((y_train == name).sum()), LABELS.index(name)))[0]
    majority, _, _ = classification_metrics(y_validation, np.full(len(y_validation), majority_class))
    comparison, class_rows, run_rows, prediction_rows, matrices, models = [], [], [], [], {}, {}
    for name in MODEL_NAMES:
        model = build_classifier(name)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            start = time.perf_counter()
            model.fit(X_train,y_train)
            fit_seconds = time.perf_counter() - start
        frozen = learned_state_hash(model)
        predicted = model.predict(X_validation)
        scores, by_class, matrix = classification_metrics(y_validation, predicted)
        by_run = []
        for run_id in sorted(validation.run_id.unique()):
            mask = validation.run_id.eq(run_id).to_numpy()
            run_scores, _, _ = classification_metrics(y_validation[mask],predicted[mask])
            by_run.append({"model":name,"run_id":run_id,"rows":int(mask.sum()),**run_scores})
        run_rows.extend(by_run)
        # Present-label F1 prevents a perfectly predicted single-class run scoring 1/3.
        stability = np.asarray([row["macro_f1_present_labels"] for row in by_run])
        timing = measure_latency(model,X_validation,predicted,batch_repeats,single_repeats)
        require(learned_state_hash(model) == frozen, "validation inference changed learned state")
        row = {"model":name,"status":STATUS,"coverage_asserted":False,
               "evaluation_split":"validation","validation_accuracy":scores["accuracy"],"validation_macro_f1":scores["macro_f1"],
               "run_macro_f1_mean":float(stability.mean()),"run_macro_f1_std":float(stability.std(ddof=0)),
               "worst_run_macro_f1":float(stability.min()), "training_seconds":fit_seconds, **timing,
               "train_rows":len(train),"validation_rows":len(validation),"train_runs":train.run_id.nunique(),
               "validation_runs":validation.run_id.nunique(),"transformed_feature_count":len(model.named_steps["preprocessing"].get_feature_names_out()),
               "numeric_scaling":"standard" if name in SCALED_MODELS else "none",
               "fit_warnings":" | ".join(str(item.message) for item in caught)}
        for item in by_class:
            row[f"{item['class'].lower()}_precision"] = item["precision"]
            row[f"{item['class'].lower()}_recall"] = item["recall"]
            class_rows.append({"model":name,**item})
        comparison.append(row)
        table = validation[["run_id","timestamp_seconds","intersection_id","approach_id"]].copy()
        table["model"],table["actual_class"],table["predicted_class"] = name,y_validation,predicted
        prediction_rows.append(table)
        matrices[name], models[name] = matrix, model
    counts = pd.DataFrame([{"split":split,"class":label,"count":int((values == label).sum()),"fraction":float((values == label).mean())}
                           for split,values in (("train",y_train),("validation",y_validation)) for label in LABELS])
    return {"comparison":pd.DataFrame(comparison),"per_class":pd.DataFrame(class_rows),"per_run":pd.DataFrame(run_rows),
            "predictions":pd.concat(prediction_rows,ignore_index=True),"class_counts":counts,"confusions":matrices,
            "models":models,"majority_reference":{"training_majority_class":majority_class,**majority}}


def save_confusions(matrices, output_dir):
    os.environ.setdefault("MPLCONFIGDIR",str(ROOT / "work/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    paths=[]
    for name,matrix in matrices.items():
        pd.DataFrame(matrix,index=pd.Index(LABELS,name="actual"),columns=LABELS).to_csv(output_dir/f"{name}_confusion.csv",lineterminator="\n")
        fig,ax=plt.subplots(figsize=(5.8,4.7))
        image=ax.imshow(matrix,cmap="Blues",vmin=0)
        for row in range(3):
            for col in range(3):
                ax.text(col,row,str(int(matrix[row,col])),ha="center",va="center",color="black",fontsize=13,
                        bbox={"boxstyle":"round,pad=0.15","facecolor":"white","edgecolor":"none","alpha":0.9})
        ax.set(xticks=range(3),yticks=range(3),xticklabels=LABELS,yticklabels=LABELS,
               xlabel="Predicted class",ylabel="Actual class",title=f"{name}: validation only")
        fig.colorbar(image,ax=ax,label="Rows")
        fig.tight_layout()
        path=output_dir/f"{name}_confusion.png"
        fig.savefig(path,dpi=150,bbox_inches="tight")
        plt.close(fig)
        paths.append(path.name)
    return paths


def run_training(splits_dir=None,output_dir=None,findings_path=None,batch_repeats=5,single_repeats=20,plots=True):
    splits_dir=Path(splits_dir or ROOT/"ml-service/data/splits")
    output_dir=Path(output_dir or ROOT/"artifacts/classification")
    frames,manifest,hashes=load_train_validation(splits_dir)  # Explicitly opens train/validation only.
    require(tuple(manifest["features"]["classification"]) == CLASSIFICATION_FEATURES,"classification feature policy mismatch")
    results=evaluate_frames(**frames,batch_repeats=batch_repeats,single_repeats=single_repeats)
    comparison=results["comparison"]
    selection=select_candidate(comparison)
    comparison["selected_candidate"]=comparison.model.eq(selection["candidate"])
    output_dir.mkdir(parents=True,exist_ok=True)
    for filename,key in (("model_comparison.csv","comparison"),("per_class_metrics.csv","per_class"),
                         ("per_run_metrics.csv","per_run"),("validation_predictions.csv","predictions"),("class_counts.csv","class_counts")):
        results[key].to_csv(output_dir/filename,index=False,lineterminator="\n")
    if plots:
        plot_paths=save_confusions(results["confusions"],output_dir)
    else:
        plot_paths=[]
        for name,matrix in results["confusions"].items():
            pd.DataFrame(matrix,index=pd.Index(LABELS,name="actual"),columns=LABELS).to_csv(output_dir/f"{name}_confusion.csv",lineterminator="\n")
    for name,model in results["models"].items():
        path=output_dir/f"{name}.joblib"
        joblib.dump(model,path)
        reloaded=joblib.load(path)
        predicted=reloaded.predict(prediction_frame(frames["validation"],"classification"))
        expected=results["predictions"].loc[results["predictions"].model.eq(name),"predicted_class"].to_numpy()
        np.testing.assert_array_equal(predicted,expected)
    joblib.dump(results["models"][selection["candidate"]],output_dir/"selected_classifier.joblib")
    (output_dir/"selected_candidate.json").write_text(json.dumps(selection,indent=2)+"\n",encoding="utf-8")
    require(hashes == {name:digest(splits_dir/name) for name in hashes},"train/validation inputs changed")
    summary={"seed":57,"syllabus_status":"UNVERIFIED","coverage_asserted":False,"status":STATUS,
             "methods":list(MODEL_NAMES),"other_models_added":[],"features":list(CLASSIFICATION_FEATURES),
             "target":"congestion_level","target_storage":"lowercase source mapped to uppercase LOW/MEDIUM/HIGH, no relabeling",
             "confusion_label_order":list(LABELS),"confusion_orientation":"rows actual, columns predicted",
             "fit_run_ids":sorted(frames["train"].run_id.unique().tolist()),
             "validation_run_ids":sorted(frames["validation"].run_id.unique().tolist()),
             "validation_prior_eda_exposure":manifest["prior_eda_exposure"]["validation"],
             "test_data_opened":False,"test_scored":False,"input_hashes_train_validation_only":hashes,
             "hyperparameter_search":False,"selection":selection,"majority_reference":results["majority_reference"],
             "class_counts":results["class_counts"].to_dict("records"),"artifact_reload_checks_passed":True,
             "latency_protocol":{"warmup":True,"batch_rows":len(frames["validation"]),"batch_repeats":batch_repeats,
                                 "single_row_repeats":single_repeats,"includes_preprocessing":True,"excludes_loading":True},
             "stability_definition":"population std across validation runs of macro-F1 over actual-or-predicted labels present in each run; fixed-three-class F1 also saved per run",
             "model_parameters":{name:model.named_steps["classifier"].get_params() for name,model in results["models"].items()},
             "plots":plot_paths,"fit_warnings":dict(zip(comparison.model,comparison.fit_warnings)),
             "versions":{"python":platform.python_version(),"numpy":np.__version__,"pandas":pd.__version__,"sklearn":sklearn.__version__},
             "training_script_sha256":digest(Path(__file__)),"syllabus_checklist_sha256":digest(ROOT/"docs/SYLLABUS_CHECKLIST.md")}
    (output_dir/"experiment_manifest.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    if findings_path is not None:
        write_findings(Path(findings_path),results,summary,output_dir)
    return results,summary


def write_findings(path,results,summary,output_dir):
    comparison=results["comparison"]
    text="""# Provisional classifier findings

Official syllabus evidence is absent. All six user-named candidates are
**PROVISIONAL / UNVERIFIED**; **no official coverage is asserted**. No additional
classifiers, model families, grid search, or validation-driven parameter changes are added.

## Split, target and leakage boundary

Use the existing seed-57 18/6/6 run split. Fit 8,712 training rows from 18 whole runs and
evaluate 2,904 validation rows from six disjoint runs. Only train.csv, validation.csv and
the split manifest are opened. test.csv is not opened, transformed, scored or used in
selection. Test IDs from the manifest are used solely for disjointness checks.

Stored low/medium/high classes are mapped to LOW/MEDIUM/HIGH, not regenerated. X is only
incoming_vehicles, outgoing_vehicles, current_phase, seconds_in_phase, time_of_day. All
identifiers, both targets, direct congestion-rule inputs and GPS sample count are excluded.
The label is still a synthetic rule-derived index. Flow/phase/time can indirectly track
its defining inputs and generator schedule, so these scores are not independent empirical
congestion discovery or evidence of real-world/GPS-only accuracy.

Imputers/encoders and optional numeric scaling are inside each fitted pipeline, trained
only on train. LogisticRegression/KNN/SVC use standard-scaled numeric features; the trees
and GaussianNB do not. Phase one-hot columns are unscaled and unknown categories are
ignored. GaussianNB applies a Gaussian/conditional-independence approximation to data
including one-hot phase fields; this assumption is imperfect and no calibration is claimed.

## Fixed candidate settings and selection

LogisticRegression: C=1, max_iter=2000, lbfgs. KNN: k=15, distance weighting, Euclidean.
GaussianNB: var_smoothing=1e-9. SVC: RBF, C=1, gamma=scale, class prediction only (no calibration).
Decision tree: depth<=8, leaf>=20. Random forest: 200 trees, depth<=12, leaf>=5,
max_features=sqrt. Random-state-capable fits use 57; KNN/forest use n_jobs=1.
These are predeclared single-fit settings, not a claim that parameters are optimal.

Selection rule fixed before training: among candidates within **0.02 absolute global
macro-F1** of the best, minimize per-run macro-F1 standard deviation; tie-break by higher
worst-run F1, then higher global F1, then name. No latency or test score selects a winner.
The selected artifact is the already train-fitted pipeline, not a train+validation refit.

Global macro-F1 always averages LOW/MEDIUM/HIGH, zero_division=0. Per-run stability uses
the union of actual/predicted classes present in that run so a perfectly predicted
single-class run does not score only 1/3. Hallucinated absent classes are included and
penalized. Fixed-three-class per-run F1 is also saved. Different class mixes affect this
stability statistic; six runs are few, and this is not random-seed robustness or a CI.

## Validation comparison

| Candidate | Accuracy | Macro-F1 | Per-run F1 std | Worst-run F1 | Fit s | Batch median ms | Amortized us/row | Single-row median ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
"""
    for row in comparison.to_dict("records"):
        text+=f"| {row['model']} | {row['validation_accuracy']:.4f} | {row['validation_macro_f1']:.4f} | {row['run_macro_f1_std']:.4f} | {row['worst_run_macro_f1']:.4f} | {row['training_seconds']:.4f} | {row['inference_batch_median_ms']:.3f} | {row['inference_amortized_us_per_row']:.3f} | {row['single_row_median_ms']:.3f} |\n"
    selected=summary["selection"]
    text+=f"\nSelected for further review: **{selected['candidate']}**, still {STATUS}. Eligible near-best candidates: {', '.join(selected['eligible_candidates'])}. This is a validation-based development choice, not a test-validated deployment recommendation.\n"
    ref=summary["majority_reference"]
    text+=f"\nReference only (not another fitted candidate): always predicting training-majority {ref['training_majority_class']} gives validation accuracy {ref['accuracy']:.4f} and macro-F1 {ref['macro_f1']:.4f}.\n"
    text+="\n### Class counts\n\n| Split | LOW | MEDIUM | HIGH |\n| --- | ---: | ---: | ---: |\n"
    for split,part in results["class_counts"].groupby("split",sort=False):
        counts=part.set_index("class")["count"]
        text+=f"| {split} | {counts['LOW']} | {counts['MEDIUM']} | {counts['HIGH']} |\n"
    text+="""
Per-class precision, recall, F1, support and predicted counts are in per_class_metrics.csv.
Confusion CSVs/PNGs are counts with **rows actual, columns predicted**, in LOW/MEDIUM/HIGH
order. Zero prediction/actual denominators use zero with support/counts disclosed.
Accuracy alone can hide the minority MEDIUM class; inspect its recall and per-run scores.

Latency includes the full preprocessing+predict path, not file loading. It uses an
excluded warmup, five full validation batches and twenty single-row calls by default.
Batch p95 is an empirical quantile of only five calls, not a service-level guarantee.
Amortized batch time per row is not single-request latency. Machine load and native
threading affect timings; n_jobs=1 does not universally fix BLAS thread count.

## Limits and reproducibility

All data is synthetic; no private/live GPS or physical signals are involved. Shared
point-queue assumptions, aligned run clocks and correlated windows limit generalization.
All approaches/windows stay in their run group. Two validation runs were explored in
prior EDA, as disclosed by the leakage audit. Test remains reserved. No claims of
controller benefits, calibrated probabilities, real-road performance or syllabus coverage
are made. Candidate selection itself uses validation, so its score is not an unbiased
final estimate. Future tuning must use grouped training folds with fresh full pipelines.
"""
    text+=f"\nArtifacts: `{output_dir}` includes model_comparison.csv, per_class_metrics.csv, per_run_metrics.csv, class_counts.csv, validation_predictions.csv, six confusion CSVs/PNGs, fitted pipelines, selected_classifier.joblib, selected_candidate.json and experiment_manifest.json. Model reloads reproduce validation predictions and input hashes are unchanged.\n"
    text+="\nReproduce: `./ml-service/.venv/Scripts/python.exe ml-service/training/train_classification.py`.\n"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding="utf-8",newline="\n")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir",type=Path,default=ROOT/"ml-service/data/splits")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"artifacts/classification")
    parser.add_argument("--findings-path",type=Path,default=ROOT/"docs/CLASSIFICATION_FINDINGS.md")
    parser.add_argument("--batch-repeats",type=int,default=5)
    parser.add_argument("--single-repeats",type=int,default=20)
    args=parser.parse_args()
    results,summary=run_training(args.splits_dir,args.output_dir,args.findings_path,args.batch_repeats,args.single_repeats)
    print(results["comparison"][["model","validation_accuracy","validation_macro_f1","run_macro_f1_std","single_row_median_ms","selected_candidate"]].to_string(index=False))
    print("Selected:",summary["selection"]["candidate"],STATUS)
    print("Test opened/scored:",summary["test_data_opened"],summary["test_scored"])
    print("Artifacts:",args.output_dir.resolve())


if __name__ == "__main__":
    main()
