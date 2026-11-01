import builtins
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest
from sklearn.cluster import AgglomerativeClustering,DBSCAN,KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from training.unsupervised import (FEATURES,ROOT,anomaly_analysis,anomaly_permissions,fit_analysis,
    hierarchical_indices,load_training,numeric_frame,profile_clusters,run_analysis,safe_silhouette)


def toy_frame(size=36):
    rng=np.random.default_rng(57)
    frame=pd.DataFrame({name:rng.normal(size=size) for name in FEATURES})
    frame["run_id"]="unit-train"
    frame["timestamp_seconds"]=np.arange(size)*10
    frame["intersection_id"]="unit-junction"
    frame["approach_id"]="north"
    frame["congestion_level"]="not-a-cluster-target"
    frame["future_wait_seconds"]=999999
    return frame


def test_only_current_numeric_inputs_are_selected_and_missing_is_imputed():
    frame=toy_frame(); frame.loc[0,"mean_speed_kmh"]=np.nan
    result=fit_analysis(frame,hierarchical_cap=20,min_samples=3)
    assert np.isfinite(result["matrix"]).all()
    assert result["matrix"].shape==(36,10)
    assert len(result["fit_rows"]["hierarchical"])==20
    assert result["models"]["PCA"].n_samples_==36
    assert result["preprocessor"].named_steps["scaler"].n_samples_seen_==36
    changed=frame.copy(); changed["congestion_level"]="changed"; changed["future_wait_seconds"]=-999999
    other=fit_analysis(changed,hierarchical_cap=20,min_samples=3)
    np.testing.assert_allclose(result["matrix"],other["matrix"])
    for method in ("KMeans","hierarchical","DBSCAN"):
        np.testing.assert_array_equal(result["labels"][method],other["labels"][method])


def test_every_fit_sees_only_training_or_disclosed_training_sample(monkeypatch):
    frame=toy_frame(36)
    calls=[]
    for cls in (SimpleImputer,StandardScaler,KMeans,AgglomerativeClustering,DBSCAN,PCA):
        original=cls.fit
        def wrapper(self,X,y=None,_original=original,_name=cls.__name__,**kwargs):
            calls.append((_name,len(X)))
            return _original(self,X,y,**kwargs)
        monkeypatch.setattr(cls,"fit",wrapper)
    fit_analysis(frame,hierarchical_cap=20,min_samples=3)
    assert dict(calls)=={"SimpleImputer":36,"StandardScaler":36,"KMeans":36,"AgglomerativeClustering":20,"DBSCAN":36,"PCA":36}


@pytest.mark.parametrize("labels",[[0,0,0],[-1,-1,-1],[0,1,2],[-1,0,0]])
def test_silhouette_is_not_fabricated_for_undefined_cases(labels):
    result=safe_silhouette(np.array([[0,0],[1,1],[2,2]]),np.array(labels))
    assert result["silhouette"] is None and result["silhouette_rows"]==0
    assert result["silhouette_status"].startswith("NOT_MEANINGFUL")


def test_silhouette_excludes_noise_and_handles_real_two_clusters():
    matrix=np.array([[0,0],[0,.1],[10,10],[10,10.1],[500,500]])
    result=safe_silhouette(matrix,np.array([0,0,1,1,-1]))
    assert result["silhouette"]>.9 and result["silhouette_rows"]==4


def test_empty_cluster_profile_retains_blank_statistics_and_explicit_status():
    frame=numeric_frame(toy_frame(4))
    result=profile_clusters(frame,np.array([0,0,2,-1]),"unit",expected_ids=[0,1,2])
    empty=result[result.cluster_id.eq(1)].iloc[0]
    assert empty.rows==0 and empty.profile_status=="EMPTY"
    assert pd.isna(empty.mean_speed_kmh_mean)
    assert result[result.cluster_id.eq(-1)].iloc[0].profile_status=="DENSITY_NOISE_NOT_GROUND_TRUTH_ANOMALY"


@pytest.mark.parametrize("size",[1,4])
def test_constant_or_one_row_inputs_do_not_invent_pca_variance_or_three_clusters(size):
    frame=toy_frame(size)
    frame.loc[:,list(FEATURES)]=1.0
    result=fit_analysis(frame,hierarchical_cap=3,min_samples=20)
    assert result["effective_k"]==1
    assert result["models"]["PCA"] is None and result["variance"].empty
    assert result["pca_status"].startswith("NOT_MEANINGFUL")
    assert result["metrics"].silhouette.isna().all()
    if size==1:
        assert result["models"]["hierarchical"] is None
        assert len(result["fit_rows"]["hierarchical"])==0
        assert result["metrics"].set_index("method").loc["hierarchical","fit_status"]=="SKIPPED_INSUFFICIENT_ROWS"
    else:
        assert result["models"]["hierarchical"] is not None
    assert (result["labels"]["DBSCAN"]==-1).all()


def test_unverified_anomaly_methods_never_fit_thresholds_or_mark_normal(monkeypatch):
    def forbidden(*args,**kwargs):
        raise RuntimeError("unverified quartile analysis ran")
    monkeypatch.setattr(np,"quantile",forbidden)
    flags,thresholds=anomaly_analysis(np.zeros((8,10)),{})
    assert thresholds=={}
    assert flags.iqr_flag.isna().all() and flags.z_score_flag.isna().all()
    assert flags.iqr_status.eq("SKIPPED_UNVERIFIED").all()
    assert flags.rationale.str.contains("not evaluated").all()


def test_method_specific_evidence_required_for_anomaly_permission(tmp_path):
    path=tmp_path/"evidence.json"
    assert anomaly_permissions(path)[0]=={}
    path.write_text(json.dumps({"topics":{"IQR":{"status":"VERIFIED","section":"2.1"}}}),encoding="utf-8")
    with pytest.raises(AssertionError,match="title/version/source"):
        anomaly_permissions(path)
    # Deliberately fake official fixture for permission-parser unit testing only.
    data={"official_syllabus":{"title":"UNIT FIXTURE","version":"1","source":"unit-test fixture, not real evidence"},
          "topics":{"IQR":{"status":"VERIFIED","section":"2.1"},"z_score":{"status":"UNVERIFIED"}}}
    path.write_text(json.dumps(data),encoding="utf-8")
    approved,_=anomaly_permissions(path)
    assert set(approved)=={"IQR"}
    data["topics"]["IQR"]["section"]=""
    path.write_text(json.dumps(data),encoding="utf-8")
    with pytest.raises(AssertionError,match="section"):
        anomaly_permissions(path)


def test_explicitly_verified_anomaly_branch_and_constant_zscore_edge_case():
    values=np.zeros((100,10)); values[-1,0]=100
    flags,stats=anomaly_analysis(values,{"IQR":{"unit_fixture":True},"z_score":{"unit_fixture":True}})
    assert bool(flags.iqr_flag.iloc[-1]) and bool(flags.z_score_flag.iloc[-1])
    assert stats["IQR"]["fit_rows"]==stats["z_score"]["fit_rows"]==100
    assert "mean_speed_kmh" in flags.rationale.iloc[-1]
    constant,_=anomaly_analysis(np.zeros((10,10)),{"z_score":{"unit_fixture":True}})
    assert constant.z_score_flag.isna().all()
    assert constant.z_score_status.eq("UNDEFINED_CONSTANT_FEATURES").all()


@pytest.mark.parametrize("bad",["empty","missing","infinite","duplicate"])
def test_invalid_inputs_fail_before_clustering(bad):
    frame=toy_frame()
    if bad=="empty": frame=frame.iloc[:0]
    elif bad=="missing": frame=frame.drop(columns=["vehicle_count"])
    elif bad=="infinite": frame.loc[0,"vehicle_count"]=np.inf
    else: frame=pd.concat([frame,frame[["vehicle_count"]]],axis=1)
    with pytest.raises(AssertionError):
        fit_analysis(frame)


def test_hierarchy_sample_is_seeded_and_training_index_only():
    frame=toy_frame(50)
    np.testing.assert_array_equal(hierarchical_indices(frame,20),hierarchical_indices(frame,20))
    assert len(hierarchical_indices(frame,20))==20
    assert set(hierarchical_indices(frame,20))<=set(range(50))
    with pytest.raises(AssertionError): hierarchical_indices(frame,0)
    with pytest.raises(AssertionError): fit_analysis(frame,eps=0)


def test_real_run_uses_train_only_even_when_heldout_files_are_missing(tmp_path,monkeypatch):
    folder=tmp_path/"inputs"; folder.mkdir()
    for name in ("train.csv","split_manifest.json"):
        shutil.copyfile(ROOT/"ml-service/data/splits"/name,folder/name)
    original=Path.open
    def guard(self,*args,**kwargs):
        if self.name in {"validation.csv","test.csv"}: raise RuntimeError("held-out data opened")
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,"open",guard)
    original_builtin=builtins.open
    def builtin_guard(file,*args,**kwargs):
        if isinstance(file,(str,Path)) and Path(file).name in {"validation.csv","test.csv"}: raise RuntimeError("held-out data opened")
        return original_builtin(file,*args,**kwargs)
    monkeypatch.setattr(builtins,"open",builtin_guard)
    result,summary=run_analysis(folder,tmp_path/"outputs",plots=False,hierarchical_cap=200)
    assert summary["fit_rows"]==8712
    assert summary["validation_data_opened"] is summary["test_data_opened"] is False
    assert summary["cluster_ids_are_ground_truth"] is summary["coverage_asserted"] is False
    assert summary["anomaly_methods"]=={"IQR":"SKIPPED_UNVERIFIED","z_score":"SKIPPED_UNVERIFIED"}
    assignments=pd.read_csv(tmp_path/"outputs/training_cluster_assignments.csv")
    assert assignments.hierarchical_in_fit.sum()==200
    assert assignments.hierarchical_cluster_id.isna().sum()==8512
    assert len(result["variance"])==10
    assert result["variance"].explained_variance_ratio.sum()==pytest.approx(1)
    flags=pd.read_csv(tmp_path/"outputs/anomaly_flags.csv")
    assert flags.iqr_flag.isna().all() and flags.z_score_flag.isna().all()
    assert flags.density_noise_flag.sum()==summary["density_noise_rows"]


def test_loader_rejects_corrupt_training_file(tmp_path):
    for name in ("train.csv","split_manifest.json"):
        shutil.copyfile(ROOT/"ml-service/data/splits"/name,tmp_path/name)
    with (tmp_path/"train.csv").open("a",encoding="utf-8") as handle: handle.write("\n")
    with pytest.raises(AssertionError,match="hash mismatch"):
        load_training(tmp_path)


def test_all_missing_numeric_column_keeps_dimension_and_profiles_do_not_invent_speed():
    frame=toy_frame()
    frame["mean_speed_kmh"]=np.nan
    result=fit_analysis(frame,hierarchical_cap=20,min_samples=3)
    assert result["matrix"].shape[1]==10
    np.testing.assert_array_equal(result["matrix"][:,0],0)
    assert result["profiles"].observed_speed_rows.eq(0).all()
    assert result["profiles"].mean_speed_kmh_mean.isna().all()


def test_completely_empty_expected_cluster_profiles_are_explicit_not_divide_by_zero():
    empty=pd.DataFrame(columns=list(FEATURES))
    result=profile_clusters(empty,np.array([],dtype=int),"empty-fit-scope",expected_ids=[0,1,2])
    assert len(result)==3
    assert result.rows.eq(0).all() and result.fraction.eq(0).all()
    assert result.profile_status.eq("EMPTY").all()
    assert result.mean_wait_seconds_mean.isna().all()
