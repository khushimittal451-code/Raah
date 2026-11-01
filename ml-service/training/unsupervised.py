"""Training-only provisional clustering/PCA; evidence-gated IQR/z-score analysis."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.cluster import AgglomerativeClustering, DBSCAN, KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"ml-service"))
from training.prepare_data import REGRESSION_FEATURES,digest,require  # noqa: E402

FEATURES=tuple(name for name in REGRESSION_FEATURES if name!="current_phase")
SEED=57
STATUS="PROVISIONAL_UNVERIFIED"
METHODS=("KMeans","hierarchical","DBSCAN")


def numeric_frame(frame):
    require(isinstance(frame,pd.DataFrame) and len(frame)>0,"training data must be a nonempty DataFrame")
    require(not frame.columns.duplicated().any(),"duplicate feature columns")
    require(set(FEATURES)<=set(frame.columns),"missing required current-time numeric fields")
    selected=frame.loc[:,list(FEATURES)].copy()
    for name in FEATURES:
        selected[name]=pd.to_numeric(selected[name],errors="raise").to_numpy(dtype=float,na_value=np.nan)
    require(not np.isinf(selected.to_numpy()).any(),"infinite measurements")
    return selected


def load_training(splits_dir):
    """Read only train.csv and manifest; never access validation.csv or test.csv."""
    splits_dir=Path(splits_dir).resolve()
    manifest_path=splits_dir/"split_manifest.json"
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest["seed"]==57 and manifest["group_column"]=="run_id","unexpected split policy")
    info=manifest["splits"]["train"]
    require(info["file"]=="train.csv","only train.csv can be opened")
    path=(splits_dir/info["file"]).resolve()
    require(path.parent==splits_dir and path.name=="train.csv","training path escapes allowed source")
    require(digest(path)==info["sha256"],"training hash mismatch")
    frame=pd.read_csv(path)
    require(len(frame)==info["rows"] and frame.run_id.nunique()==info["groups"] and set(frame.run_id)==set(info["run_ids"]),"training membership/count mismatch")
    for heldout in ("validation","test"):
        require(not set(frame.run_id)&set(manifest["splits"][heldout]["run_ids"]),"training overlaps declared held-out groups")
    numeric_frame(frame)
    return frame,manifest,{"train.csv":digest(path),"split_manifest.json":digest(manifest_path)}


def anomaly_permissions(path=None):
    """User-supplied explicit official verification evidence, absent by default.

    Shape: official_syllabus {title,version,source}, topics {IQR/z_score:
    {status: VERIFIED, section: ...}}. No generic 'outlier detection' approval inferred.
    """
    path=Path(path or ROOT/"docs/syllabus_verification.json")
    if not path.is_file():
        return {},"No official method-specific syllabus verification file provided"
    data=json.loads(path.read_text(encoding="utf-8"))
    official=data.get("official_syllabus",{})
    require(all(isinstance(official.get(key),str) and official[key].strip() for key in ("title","version","source")),"official syllabus title/version/source required")
    approved={}
    for method in ("IQR","z_score"):
        topic=data.get("topics",{}).get(method,{})
        if topic.get("status")=="VERIFIED":
            require(isinstance(topic.get("section"),str) and topic["section"].strip(),"exact official section required for anomaly approval")
            approved[method]={"official_syllabus":official,"section":topic["section"],"evidence_sha256":digest(path)}
    return approved,"Only explicitly VERIFIED method-specific entries are enabled"


def anomaly_analysis(imputed,approved):
    require(set(approved)<={"IQR","z_score"},"unrecognized anomaly method")
    values=np.asarray(imputed,dtype=float)
    require(values.ndim==2 and len(values)>0 and values.shape[1]==len(FEATURES) and np.isfinite(values).all(),"invalid anomaly matrix")
    output=pd.DataFrame(index=range(len(values)))
    statistics={}
    reasons=[[] for _ in range(len(values))]
    for method,prefix in (("IQR","iqr"),("z_score","z_score")):
        if method not in approved:
            output[prefix+"_flag"]=pd.array([pd.NA]*len(values),dtype="boolean")
            output[prefix+"_status"]="SKIPPED_UNVERIFIED"
            for reason in reasons:
                reason.append(method+": not evaluated; official method-specific permission absent")
            continue
        if method=="IQR":
            q1,q3=np.quantile(values,[.25,.75],axis=0)
            lower,upper=q1-1.5*(q3-q1),q3+1.5*(q3-q1)
            flags=(values<lower)|(values>upper)
            statistics[method]={"q1":q1.tolist(),"q3":q3.tolist(),"lower":lower.tolist(),"upper":upper.tolist(),"fit_rows":len(values),"evidence":approved[method]}
        else:
            mean,std=values.mean(axis=0),values.std(axis=0,ddof=0)
            usable=std>0
            statistics[method]={"mean":mean.tolist(),"std_ddof0":std.tolist(),"threshold":3.0,"fit_rows":len(values),"zero_variance_features":[FEATURES[i] for i in np.flatnonzero(~usable)],"evidence":approved[method]}
            if not usable.any():
                output[prefix+"_flag"]=pd.array([pd.NA]*len(values),dtype="boolean")
                output[prefix+"_status"]="UNDEFINED_CONSTANT_FEATURES"
                for reason in reasons:
                    reason.append("z_score: undefined because all training features are constant")
                continue
            z=np.zeros_like(values)
            z[:,usable]=(values[:,usable]-mean[usable])/std[usable]
            flags=np.abs(z)>3
        output[prefix+"_flag"]=flags.any(axis=1)
        output[prefix+"_status"]="EVALUATED_TRAIN_ONLY"
        for index,row in enumerate(flags):
            names=[FEATURES[column] for column in np.flatnonzero(row)]
            reasons[index].append(method+": "+(",".join(names) if names else "no threshold exceedance; not proof of normality"))
    output["rationale"]=["; ".join(parts) for parts in reasons]
    return output,statistics


def profile_clusters(raw,labels,method,expected_ids):
    require(len(raw)==len(labels),"cluster/profile row mismatch")
    labels=np.asarray(labels)
    result=[]
    for cluster in sorted(set(expected_ids)|set(labels.tolist())):
        part=raw.iloc[np.flatnonzero(labels==cluster)]
        row={"method":method,"cluster_id":int(cluster),"rows":len(part),"fraction":len(part)/len(raw) if len(raw) else 0,
             "profile_status":"EMPTY" if len(part)==0 else ("DENSITY_NOISE_NOT_GROUND_TRUTH_ANOMALY" if cluster==-1 else "ARBITRARY_CLUSTER_ID"),
             "observed_speed_rows":int(part.mean_speed_kmh.notna().sum())}
        for name in FEATURES:
            row[name+"_mean"]=float(part[name].mean()) if part[name].notna().any() else None
            row[name+"_median"]=float(part[name].median()) if part[name].notna().any() else None
        result.append(row)
    return pd.DataFrame(result)


def safe_silhouette(matrix,labels,max_rows=1500):
    matrix=np.asarray(matrix); labels=np.asarray(labels)
    require(len(matrix)==len(labels),"silhouette row mismatch")
    require(type(max_rows) is int and max_rows>=3,"silhouette cap must be >=3")
    keep=labels!=-1  # DBSCAN noise is not treated as a legitimate cluster.
    X,y=matrix[keep],labels[keep]
    clusters=len(np.unique(y))
    result={"silhouette":None,"silhouette_rows":0,"silhouette_status":""}
    if len(y)<3 or not 2<=clusters<len(y):
        result["silhouette_status"]="NOT_MEANINGFUL: need >=2 non-noise clusters and fewer clusters than rows"
        return result
    if len(y)>max_rows:
        indices=np.sort(np.random.default_rng(57).choice(len(y),max_rows,replace=False))
        X,y=X[indices],y[indices]
    if len(np.unique(y))!=clusters or len(np.unique(y))>=len(y):
        result["silhouette_status"]="NOT_MEANINGFUL: seeded sample omits a cluster or has all singleton labels"
        return result
    result.update(silhouette=float(silhouette_score(X,y)),silhouette_rows=len(y),silhouette_status="TRAIN_ONLY_SAMPLED" if keep.sum()>max_rows else "TRAIN_ONLY_FULL")
    return result


def hierarchical_indices(frame,cap=2000):
    require(type(cap) is int and cap>=3,"hierarchical cap must be >=3")
    if len(frame)<=cap:
        return np.arange(len(frame))
    # Seeded uniform training sample; no target/scenario/held-out values select rows.
    return np.sort(np.random.default_rng(57).choice(len(frame),cap,replace=False))


def fit_analysis(frame,approved=None,hierarchical_cap=2000,eps=1.2,min_samples=20):
    raw=numeric_frame(frame)
    require(np.isfinite(eps) and eps>0 and type(min_samples) is int and min_samples>=1,"invalid DBSCAN configuration")
    hierarchy_rows=hierarchical_indices(frame,hierarchical_cap)
    imputer=SimpleImputer(strategy="median",keep_empty_features=True)
    scaler=StandardScaler()
    preprocessor=Pipeline([("imputer",imputer),("scaler",scaler)])
    X=preprocessor.fit_transform(raw)
    imputed=imputer.transform(raw)
    require(np.isfinite(X).all(),"nonfinite preprocessed training data")
    unique=len(np.unique(X,axis=0))
    effective_k=min(3,len(X),unique)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        kmeans=KMeans(n_clusters=effective_k,n_init=20,random_state=57,algorithm="lloyd").fit(X)
    hierarchy_k=min(3,len(hierarchy_rows),len(np.unique(X[hierarchy_rows],axis=0)))
    if len(hierarchy_rows)>=2:
        hierarchical=AgglomerativeClustering(n_clusters=hierarchy_k,linkage="ward").fit(X[hierarchy_rows])
        hierarchy_labels=hierarchical.labels_
    else:
        hierarchical=None
        hierarchy_rows=np.array([],dtype=int)
        hierarchy_labels=np.array([],dtype=int)
        hierarchy_k=0
    dbscan=DBSCAN(eps=eps,min_samples=min_samples,n_jobs=1).fit(X)
    if len(X)>=2 and np.var(X,axis=0).sum()>0:
        pca=PCA(n_components=min(len(X),X.shape[1]),svd_solver="full",random_state=57).fit(X)
        transformed=pca.transform(X)
        coords=np.column_stack([transformed[:,0],transformed[:,1] if transformed.shape[1]>1 else np.zeros(len(X))])
        variance=pd.DataFrame({"component":np.arange(1,pca.n_components_+1),"explained_variance_ratio":pca.explained_variance_ratio_,"cumulative_explained_variance":np.cumsum(pca.explained_variance_ratio_)})
        pca_status="FITTED_TRAIN_ONLY"
    else:
        pca=None; coords=np.zeros((len(X),2)); variance=pd.DataFrame(columns=["component","explained_variance_ratio","cumulative_explained_variance"])
        pca_status="NOT_MEANINGFUL: fewer than two rows or all features constant"
    labels={"KMeans":kmeans.labels_,"hierarchical":hierarchy_labels,"DBSCAN":dbscan.labels_}
    fit_rows={"KMeans":np.arange(len(X)),"hierarchical":hierarchy_rows,"DBSCAN":np.arange(len(X))}
    profiles=[]; metrics=[]
    for method in METHODS:
        indices=fit_rows[method]; assignment=labels[method]
        expected=range(effective_k if method=="KMeans" else hierarchy_k) if method!="DBSCAN" else set(assignment)
        profiles.append(profile_clusters(raw.iloc[indices].reset_index(drop=True),assignment,method,expected))
        metrics.append({"method":method,"status":STATUS,"fit_status":"SKIPPED_INSUFFICIENT_ROWS" if method=="hierarchical" and hierarchical is None else "FITTED_TRAIN_ONLY","requested_clusters":3 if method!="DBSCAN" else None,
                        "effective_nonnoise_clusters":len(set(assignment)-{-1}),"fit_rows":len(indices),"noise_rows":int((assignment==-1).sum()),
                        **safe_silhouette(X[indices],assignment)})
    flags,thresholds=anomaly_analysis(imputed,approved or {})
    flags["dbscan_cluster_id"]=dbscan.labels_
    flags["density_noise_flag"]=dbscan.labels_==-1
    flags["rationale"]+=["; DBSCAN: density-unassigned (-1), not a confirmed anomaly" if value else "; DBSCAN: assigned density cluster, not proof of normality" for value in flags.density_noise_flag]
    return {"preprocessor":preprocessor,"matrix":X,"models":{"KMeans":kmeans,"hierarchical":hierarchical,"DBSCAN":dbscan,"PCA":pca},
            "labels":labels,"fit_rows":fit_rows,"profiles":pd.concat(profiles,ignore_index=True),"metrics":pd.DataFrame(metrics),
            "coords":coords,"variance":variance,"pca_status":pca_status,"flags":flags,"thresholds":thresholds,
            "kmeans_warnings":[str(item.message) for item in caught],"effective_k":effective_k}


def make_plots(frame,result,output_dir):
    os.environ.setdefault("MPLCONFIGDIR",str(ROOT/"work/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    paths=[]
    for number,method in enumerate(METHODS,1):
        rows=result["fit_rows"][method]
        labels=result["labels"][method]
        fig,ax=plt.subplots(figsize=(7,5))
        for cluster in sorted(set(labels)) if result["models"]["PCA"] is not None else []:
            indices=rows[labels==cluster]
            if len(indices)>2500:
                indices=np.sort(np.random.default_rng(57).choice(indices,2500,replace=False))
            xy=result["coords"][indices]
            ax.scatter(xy[:,0],xy[:,1],s=8,alpha=.4,label="Density noise (-1)" if cluster==-1 else f"Cluster {cluster}",color="black" if cluster==-1 else None)
        ax.set(title=f"{method}: training clusters, PCA view only",xlabel="Training PC1",ylabel="Training PC2")
        if result["models"]["PCA"] is not None:
            ax.legend(markerscale=2,fontsize=8)
        else:
            ax.text(.5,.5,"PCA projection unavailable: insufficient rows or constant features",ha="center",wrap=True,transform=ax.transAxes)
        fig.tight_layout(); path=output_dir/f"{number:02d}_{method}_pca2d.png"
        fig.savefig(path,dpi=150,bbox_inches="tight"); plt.close(fig); paths.append(path.name)
    fig,ax=plt.subplots(figsize=(7,5))
    if result["models"]["PCA"] is not None:
        points=ax.scatter(result["coords"][:,0],result["coords"][:,1],c=frame.queue_length_vehicles,s=7,alpha=.35,cmap="viridis")
        fig.colorbar(points,ax=ax,label="Current queued vehicles (input, not target)")
    else:
        ax.text(.5,.5,"PCA projection unavailable: insufficient rows or constant features",ha="center",wrap=True,transform=ax.transAxes)
    ax.set(title="Training PCA projection: current queue",xlabel="Training PC1",ylabel="Training PC2")
    fig.tight_layout(); path=output_dir/"04_PCA_training_2d.png"
    fig.savefig(path,dpi=150,bbox_inches="tight"); plt.close(fig); paths.append(path.name)
    fig,axes=plt.subplots(1,2,figsize=(10,3.8))
    variance=result["variance"]
    if len(variance):
        axes[0].bar(variance.component,variance.explained_variance_ratio,color="#277b70")
        axes[1].plot(variance.component,variance.cumulative_explained_variance,marker="o",color="#c98b44")
    else:
        axes[0].text(.5,.5,result["pca_status"],ha="center",wrap=True,transform=axes[0].transAxes)
    axes[0].set(title="PCA explained variance (training)",xlabel="Component",ylabel="Variance ratio")
    axes[1].set(title="Cumulative explained variance",xlabel="Components",ylabel="Cumulative ratio",ylim=(0,1.02))
    fig.tight_layout(); path=output_dir/"05_PCA_explained_variance.png"
    fig.savefig(path,dpi=150,bbox_inches="tight"); plt.close(fig); paths.append(path.name)
    return paths


def run_analysis(splits_dir=None,output_dir=None,findings_path=None,approval_path=None,plots=True,hierarchical_cap=2000):
    splits_dir=Path(splits_dir or ROOT/"ml-service/data/splits")
    output_dir=Path(output_dir or ROOT/"artifacts/unsupervised")
    frame,manifest,hashes=load_training(splits_dir)
    approved,approval_note=anomaly_permissions(approval_path)
    result=fit_analysis(frame,approved,hierarchical_cap)
    output_dir.mkdir(parents=True,exist_ok=True)
    identity=frame[["run_id","timestamp_seconds","intersection_id","approach_id"]].reset_index(drop=True)
    assignments=identity.copy()
    assignments["kmeans_cluster_id"]=result["labels"]["KMeans"]
    assignments["dbscan_cluster_id"]=result["labels"]["DBSCAN"]
    assignments["hierarchical_cluster_id"]=pd.array([pd.NA]*len(frame),dtype="Int64")
    assignments.loc[result["fit_rows"]["hierarchical"],"hierarchical_cluster_id"]=result["labels"]["hierarchical"]
    assignments["hierarchical_in_fit"]=assignments.hierarchical_cluster_id.notna()
    assignments.to_csv(output_dir/"training_cluster_assignments.csv",index=False,lineterminator="\n")
    result["profiles"].to_csv(output_dir/"cluster_profiles.csv",index=False,lineterminator="\n")
    result["metrics"].to_csv(output_dir/"cluster_metrics.csv",index=False,lineterminator="\n")
    result["variance"].to_csv(output_dir/"pca_explained_variance.csv",index=False,lineterminator="\n")
    coordinates=identity.copy(); coordinates[["PC1","PC2"]]=result["coords"]
    coordinates.to_csv(output_dir/"pca_training_coordinates.csv",index=False,lineterminator="\n")
    flags=pd.concat([identity,result["flags"]],axis=1)
    flags.to_csv(output_dir/"anomaly_flags.csv",index=False,lineterminator="\n")
    plot_paths=make_plots(frame,result,output_dir) if plots else []
    joblib.dump({"preprocessor":result["preprocessor"],"models":result["models"],"anomaly_thresholds":result["thresholds"]},output_dir/"training_unsupervised.joblib")
    require(hashes=={name:digest(splits_dir/name) for name in hashes},"training inputs changed")
    summary={"seed":57,"status":STATUS,"coverage_asserted":False,"fit_rows":len(frame),"fit_run_ids":sorted(frame.run_id.unique().tolist()),
             "features":list(FEATURES),"cluster_ids_are_ground_truth":False,"validation_data_opened":False,"test_data_opened":False,
             "input_hashes_training_only":hashes,"requested_k":3,"effective_k":result["effective_k"],
             "hierarchical_status":"FITTED_TRAIN_ONLY" if result["models"]["hierarchical"] is not None else "SKIPPED_INSUFFICIENT_ROWS",
             "hierarchical_fit_rows":len(result["fit_rows"]["hierarchical"]),"hierarchical_sample_indices":result["fit_rows"]["hierarchical"].tolist(),
             "hierarchical_full_training_assignments_invented":False,"dbscan_parameters":{"eps":1.2,"min_samples":20},
             "density_noise_rows":int(flags.density_noise_flag.sum()),"pca_status":result["pca_status"],
             "pca_two_component_variance":float(result["variance"].explained_variance_ratio.iloc[:2].sum()) if len(result["variance"]) else None,
             "anomaly_methods":{method:("EVALUATED_TRAIN_ONLY" if method in approved else "SKIPPED_UNVERIFIED") for method in ("IQR","z_score")},
             "anomaly_approval_note":approval_note,"anomaly_thresholds":result["thresholds"],"plots":plot_paths,"warnings":result["kmeans_warnings"],
             "scope":"descriptive training-only patterns; no label accuracy or anomaly ground truth asserted",
             "versions":{"python":platform.python_version(),"numpy":np.__version__,"pandas":pd.__version__,"sklearn":sklearn.__version__},
             "script_sha256":digest(Path(__file__))}
    (output_dir/"analysis_manifest.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    if findings_path is not None:
        write_findings(Path(findings_path),summary,result["metrics"],result["profiles"],output_dir)
    return result,summary


def write_findings(path,summary,metrics,profiles,output_dir):
    text="""# Unsupervised findings

All named clustering/PCA methods are **PROVISIONAL / UNVERIFIED**. No official
syllabus coverage is asserted. **Cluster IDs are arbitrary, not LOW/MEDIUM/HIGH
ground-truth labels**. No label accuracy, ARI or other supervised cluster score is used.

Only the manifest's 8,712 rows from 18 training runs are loaded. Neither validation.csv
nor test.csv is opened, transformed or fitted. Numeric median imputation and standard
scaling fit exclusively on training. The ten current-time numeric fields exclude IDs,
phase categories, congestion_level and future_wait_seconds. Original inputs are unchanged.

## Fixed methods and scope

- K-Means: requested k=3, n_init=20, seed 57, Lloyd. k is reduced explicitly only when
  rows/distinct training vectors are fewer than three; effective k is recorded.
- Hierarchical: Ward/Euclidean on a seed-57 uniform training sample capped at 2,000 rows,
  bounding quadratic memory. Unselected rows have blank hierarchical assignments; no
  nearest-centroid or other out-of-sample labeling method is silently introduced.
- DBSCAN: eps=1.2, min_samples=20 on training-standardized inputs. -1 is unassigned
  density noise, **not a ground-truth anomaly**. Parameters are not tuned using labels
  or held-out sets. Distance-based methods are sensitive to scale and correlated fields.
- PCA: full SVD fitted on all training rows, with per-component/cumulative variance saved.
  Clustering fits the ten-dimensional standardized data, not the 2D plot coordinates.
  Two-dimensional visual separation can distort the full-space structure.

Silhouette excludes DBSCAN noise, uses at most 1,500 seeded training rows, and is left
blank with a rationale for one/all-noise/all-singleton clusters or unsuitable samples.
It is descriptive geometry, not congestion-label correctness or an objective for tuning.

| Method | Fit rows | Non-noise clusters | Noise rows | Silhouette | Status |
| --- | ---: | ---: | ---: | ---: | --- |
"""
    for row in metrics.to_dict("records"):
        score="not meaningful" if pd.isna(row["silhouette"]) else f"{row['silhouette']:.4f}"
        text+=f"| {row['method']} | {row['fit_rows']} | {row['effective_nonnoise_clusters']} | {row['noise_rows']} | {score} | {row['silhouette_status']} |\n"
    text+=f"\nPCA first-two-component explained variance: {100*summary['pca_two_component_variance']:.2f}%. Cluster profiles report counts and original-unit mean/median values; speed summaries use available observations, so sampling coverage can bias them. Empty expected clusters retain explicit EMPTY rows and blank statistics.\n" if summary['pca_two_component_variance'] is not None else "\nPCA variance is not meaningful for this degenerate dataset.\n"
    text+="""
## Anomaly gating and rationale

IQR and z-score are **SKIPPED_UNVERIFIED** in the current project: no official
method-specific approval file is present. Their flag cells are blank, not False/normal.
No IQR/z-score statistics are fitted. anomaly_flags.csv includes per-row skip rationale
and a separate DBSCAN density-noise flag; no observations are deleted. A generic
UNVERIFIED outlier-detection topic does not authorize either method.

The optional approval loader requires a retained official title/version/source and
explicit VERIFIED IQR or z_score topic plus exact section. This records user-provided
verification evidence; it does not autonomously authenticate a syllabus document.
If explicitly verified later, IQR uses training-imputed original-unit quartiles and 1.5
IQR fences; z-score uses training mean/population std and |z|>3. Constant-feature cases
are documented rather than divided by zero, and no held-out thresholds are learned.

## Interpretation and limits

The data is synthetic, not live GPS. Counts, queues and waits are simulator truth.
Correlated counts/queues/waits/sample coverage may dominate Euclidean geometry; clusters
can reflect demand magnitude, generator configuration, clock and fixed virtual timing.
Labels elsewhere are feature-derived, so comparing clusters to those labels would be
circular evidence, not independent traffic discovery. Different seeds/parameters can
change arbitrary cluster numbers; no cluster stability or real-road validity is claimed.
The hierarchy sample and silhouette sample are disclosed and may omit rare behavior.
No controller, model selection or raw-data filtering uses these cluster/noise IDs.
"""
    if any(value=="EVALUATED_TRAIN_ONLY" for value in summary["anomaly_methods"].values()):
        text=text.replace("IQR and z-score are **SKIPPED_UNVERIFIED** in the current project: no official\nmethod-specific approval file is present. Their flag cells are blank, not False/normal.\nNo IQR/z-score statistics are fitted.",
                          "Method-specific user-provided verification evidence was supplied. Actual statuses: " + json.dumps(summary["anomaly_methods"]) + ". Only approved methods fit training thresholds; skipped flags remain blank.")
    text+=f"\nArtifacts: `{output_dir}` contains profiles, metrics, assignments, PCA variance/coordinates, anomaly flags with rationale, five PNGs, fitted training objects and analysis_manifest.json. Reproduce with `./ml-service/.venv/Scripts/python.exe ml-service/training/unsupervised.py`.\n"
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(text,encoding="utf-8",newline="\n")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--splits-dir",type=Path,default=ROOT/"ml-service/data/splits")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"artifacts/unsupervised")
    parser.add_argument("--findings-path",type=Path,default=ROOT/"docs/UNSUPERVISED_FINDINGS.md")
    args=parser.parse_args()
    result,summary=run_analysis(args.splits_dir,args.output_dir,args.findings_path)
    print(result["metrics"].to_string(index=False))
    print("PCA two-component variance:",summary["pca_two_component_variance"])
    print("Anomaly methods:",summary["anomaly_methods"])
    print("Validation/test opened:",summary["validation_data_opened"],summary["test_data_opened"])


if __name__=="__main__":
    main()
