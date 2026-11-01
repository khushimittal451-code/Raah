from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from training.prepare_data import (
    CLASSIFICATION_FEATURES, REGRESSION_FEATURES, ROOT, audit_feature_lists,
    audit_groups, legacy_eda_map, prepare_data, read_csv, split_groups,
)

DATA = ROOT / "ml-service/data"


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    output = tmp_path_factory.mktemp("prepared-splits")
    manifest = prepare_data(DATA, output)
    return output, manifest


def test_exact_60_20_20_groups_all_rows_and_no_eda_test_exposure(prepared):
    _, manifest = prepared
    assert [(manifest["splits"][name]["groups"], manifest["splits"][name]["rows"])
            for name in ("train", "validation", "test")] == [(18, 8712), (6, 2904), (6, 2904)]
    groups = {name: set(info["run_ids"]) for name, info in manifest["splits"].items()}
    assert not (groups["train"] & groups["validation"] or groups["train"] & groups["test"] or groups["validation"] & groups["test"])
    assert len(set.union(*groups.values())) == 30
    assert len(manifest["prior_eda_exposure"]["validation"]) == 2
    assert manifest["prior_eda_exposure"]["test"] == []
    assert manifest["checks"]["preprocessing_fitted"] is False
    assert manifest["checks"]["future_labels_exact_same_group"]


def test_raw_split_union_preserves_all_cells_nulls_and_neighboring_rows(prepared):
    output, manifest = prepared
    fields, original = read_csv(DATA / "traffic_observations.csv")
    union = []
    observed_membership = {}
    for name in ("train", "validation", "test"):
        columns, rows = read_csv(output / f"{name}.csv")
        assert columns == fields
        for row in rows:
            if row["run_id"] in observed_membership:
                assert observed_membership[row["run_id"]] == name
            observed_membership[row["run_id"]] = name
        assert set(observed_membership) <= {row["run_id"] for row in original}
        counts = Counter(row["run_id"] for row in rows)
        assert all(count == 121 * 4 for count in counts.values())
        assert {row["approach_id"] for row in rows} == {"north", "south", "east", "west"}
        union.extend(tuple(row[field] for field in fields) for row in rows)
        assert hashlib.sha256((output / f"{name}.csv").read_bytes()).hexdigest() == manifest["splits"][name]["sha256"]
    assert Counter(union) == Counter(tuple(row[field] for field in fields) for row in original)
    assert sum(row[fields.index("mean_speed_kmh")] == "" for row in union) == 2761
    for filename, fingerprint in manifest["source_sha256"].items():
        assert hashlib.sha256((DATA / filename).read_bytes()).hexdigest() == fingerprint


def test_seeded_splits_and_manifest_reproduce_without_ignored_eda_artifact(prepared, tmp_path):
    output, _ = prepared
    repeat = tmp_path / "repeat"
    prepare_data(DATA, repeat, prior_map_path=tmp_path / "absent-eda.csv")
    for name in ("train.csv", "validation.csv", "test.csv", "split_manifest.json"):
        assert (output / name).read_bytes() == (repeat / name).read_bytes(), name


def test_metadata_order_cannot_change_group_membership():
    _, metadata = read_csv(DATA / "run_metadata.csv")
    assert split_groups(metadata) == split_groups(list(reversed(metadata)))
    with pytest.raises(AssertionError, match="seed"):
        split_groups(metadata, seed=58)


@pytest.mark.parametrize("feature", ["run_id", "intersection_id", "approach_id", "timestamp_seconds",
    "congestion_level", "future_wait_seconds", "mean_speed_kmh", "free_flow_speed_kmh",
    "vehicle_count", "queue_length_vehicles", "mean_wait_seconds", "gps_sample_count",
    "speed_ratio", "congestion_score", "future_incoming_vehicles"])
def test_classification_rejects_identifiers_targets_rule_inputs_and_derived_features(feature):
    with pytest.raises(AssertionError):
        audit_feature_lists(classification=CLASSIFICATION_FEATURES + (feature,))


@pytest.mark.parametrize("feature", ["run_id", "timestamp_seconds", "congestion_level",
    "future_wait_seconds", "future_phase", "target_mean_wait", "scenario_type", "run_seed"])
def test_regression_rejects_metadata_and_post_outcome_features(feature):
    with pytest.raises(AssertionError):
        audit_feature_lists(regression=REGRESSION_FEATURES + (feature,))


def test_current_wait_is_permitted_only_for_future_regression_not_classification():
    assert "mean_wait_seconds" in REGRESSION_FEATURES
    assert "mean_wait_seconds" not in CLASSIFICATION_FEATURES
    assert audit_feature_lists()


@pytest.mark.parametrize("groups", [
    {"train": {"a", "b"}, "validation": {"b"}, "test": {"c"}},
    {"train": {"a"}, "validation": {"b"}, "test": {"c"}},
    {"train": {"a", "b"}, "validation": set(), "test": {"c", "d"}},
])
def test_group_overlap_missing_runs_and_empty_split_fail(groups):
    with pytest.raises(AssertionError):
        audit_groups(groups, {"a", "b", "c", "d"})


def copy_source(tmp_path):
    folder = tmp_path / "source"
    folder.mkdir()
    for name in ("traffic_observations.csv", "run_metadata.csv", "traffic_source_snapshots.csv"):
        shutil.copyfile(DATA / name, folder / name)
    return folder


def overwrite_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_corrupt_future_wait_fails_before_creating_split_outputs(tmp_path):
    folder = copy_source(tmp_path)
    path = folder / "traffic_observations.csv"
    fields, rows = read_csv(path)
    rows[0]["future_wait_seconds"] = str(float(rows[0]["future_wait_seconds"]) + 1)
    overwrite_csv(path, fields, rows)
    output = tmp_path / "blocked"
    with pytest.raises(AssertionError, match="future target"):
        prepare_data(folder, output)
    assert not output.exists()


def test_duplicate_run_seed_fails_before_writing(tmp_path):
    folder = copy_source(tmp_path)
    path = folder / "run_metadata.csv"
    fields, rows = read_csv(path)
    rows[1]["run_seed"] = rows[0]["run_seed"]
    overwrite_csv(path, fields, rows)
    with pytest.raises(AssertionError, match="run seeds"):
        prepare_data(folder, tmp_path / "blocked")


def test_disagreement_with_prior_eda_history_fails_closed(tmp_path):
    _, metadata = read_csv(DATA / "run_metadata.csv")
    rows = [{"run_id": run, "split": split} for run, split in sorted(legacy_eda_map(metadata).items())]
    fields = ["run_id", "split"]
    rows[0]["split"] = "test" if rows[0]["split"] != "test" else "train"
    path = tmp_path / "wrong-eda.csv"
    overwrite_csv(path, fields, rows)
    with pytest.raises(AssertionError, match="prior EDA map disagrees"):
        prepare_data(DATA, tmp_path / "blocked", prior_map_path=path)


def test_source_directory_is_not_an_output_directory():
    with pytest.raises(AssertionError, match="source directory"):
        prepare_data(DATA, DATA)
