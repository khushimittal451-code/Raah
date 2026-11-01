"""Raw, run-separated splits. No model or preprocessing is fitted here."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml-service"))
from app.schemas import LabeledTrafficRecord, RunProvenance, TrafficObservation  # noqa: E402

SEED = 57
TARGETS = {"congestion_level", "future_wait_seconds"}
IDENTIFIERS = {"run_id", "intersection_id", "approach_id", "timestamp_seconds"}
RULE_INPUTS = {"mean_speed_kmh", "free_flow_speed_kmh", "vehicle_count", "queue_length_vehicles", "mean_wait_seconds"}
CLASSIFICATION_FEATURES = ("incoming_vehicles", "outgoing_vehicles", "current_phase", "seconds_in_phase", "time_of_day")
REGRESSION_FEATURES = (
    "mean_speed_kmh", "free_flow_speed_kmh", "vehicle_count", "queue_length_vehicles",
    "mean_wait_seconds", "incoming_vehicles", "outgoing_vehicles", "current_phase",
    "seconds_in_phase", "time_of_day", "gps_sample_count",
)
INTEGER_FIELDS = {"timestamp_seconds", "vehicle_count", "queue_length_vehicles", "incoming_vehicles", "outgoing_vehicles", "gps_sample_count"}
NUMBER_FIELDS = {"mean_speed_kmh", "free_flow_speed_kmh", "mean_wait_seconds", "seconds_in_phase", "time_of_day", "future_wait_seconds"}


def require(condition, message):
    # Explicit checks remain active under python -O, unlike bare assert statements.
    if not condition:
        raise AssertionError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    require(bool(rows), f"empty input: {path}")
    require(fields and len(fields) == len(set(fields)), "duplicate or missing CSV headers")
    require(all(None not in row and all(value is not None for value in row.values()) for row in rows), "malformed CSV row")
    return fields, rows


def typed(row):
    return {key: (int(value) if key in INTEGER_FIELDS else (float(value) if value else None))
            if key in INTEGER_FIELDS | NUMBER_FIELDS else value for key, value in row.items()}


def audit_feature_lists(classification=CLASSIFICATION_FEATURES, regression=REGRESSION_FEATURES):
    for task, names, allowed in (("classification", classification, set(CLASSIFICATION_FEATURES)),
                                 ("regression", regression, set(REGRESSION_FEATURES))):
        require(bool(names) and len(names) == len(set(names)), f"empty/duplicate {task} features")
        require(not set(names) & (TARGETS | IDENTIFIERS), f"target or identifier leakage in {task}")
        require(set(names) <= allowed, f"unapproved, derived or post-outcome feature in {task}")
    require(not set(classification) & RULE_INPUTS, "classification includes direct congestion-rule inputs")
    require("gps_sample_count" not in classification, "classification includes a close vehicle-count proxy")
    return True


def legacy_eda_map(metadata, seed=57):
    """Reconstruct the existing notebook's feature-blind 4/1/rest run policy."""
    rng = np.random.default_rng(seed)
    by_scenario = defaultdict(list)
    for row in metadata:
        by_scenario[row["scenario_type"]].append(row["run_id"])
    require(all(len(ids) >= 6 for ids in by_scenario.values()), "need >=6 runs per scenario to retain prior EDA holdouts")
    mapping = {}
    for scenario in sorted(by_scenario):
        for index, run_id in enumerate(rng.permutation(sorted(by_scenario[scenario]))):
            mapping[str(run_id)] = "train" if index < 4 else ("validation" if index == 4 else "test")
    return mapping


def split_groups(metadata, seed=57):
    require(type(seed) is int and seed == 57, "split seed must be 57")
    ids = sorted(row["run_id"] for row in metadata)
    require(len(ids) == len(set(ids)), "duplicate metadata run_id")
    require(len(ids) >= 30, "at least 30 independent runs required")
    prior = legacy_eda_map(metadata, seed)
    scenario = {row["run_id"]: row["scenario_type"] for row in metadata}
    rng = np.random.default_rng(seed)
    shuffled = lambda values: [str(value) for value in rng.permutation(sorted(values))]
    n_train, n_test = round(0.6 * len(ids)), round(0.2 * len(ids))
    prior_train = {run for run, split in prior.items() if split == "train"}
    prior_test = {run for run, split in prior.items() if split == "test"}
    prior_val = {run for run, split in prior.items() if split == "validation"}
    # Prefer the original untouched test set, then other never-explored validation runs.
    test = set((shuffled(prior_test) + shuffled(prior_val))[:n_test])
    require(len(test) == n_test and not test & prior_train, "insufficient unexplored groups for clean final test")
    clean_remaining = (set(ids) - prior_train) - test
    if n_train <= len(prior_train):
        removed = set()
        remove_count = len(prior_train) - n_train
        # If a scenario's old validation run becomes test, reserve a different run
        # from that scenario for validation, without reading feature/target values.
        missing_validation_scenarios = set(scenario.values()) - {scenario[run] for run in clean_remaining}
        for name in sorted(missing_validation_scenarios):
            if len(removed) < remove_count:
                candidates = {run for run in prior_train - removed if scenario[run] == name}
                removed.add(shuffled(candidates)[0])
        while len(removed) < remove_count:
            counts = Counter(scenario[run] for run in prior_train - removed)
            largest = max(counts.values())
            candidates = {run for run in prior_train - removed if counts[scenario[run]] == largest}
            removed.add(shuffled(candidates)[0])
        train = prior_train - removed
    else:
        train = prior_train | set(shuffled(clean_remaining)[:n_train - len(prior_train)])
    validation = set(ids) - train - test
    groups = {"train": train, "validation": validation, "test": test}
    audit_groups(groups, set(ids))
    require(len(train) == n_train and len(test) == n_test, "requested group counts not attained")
    return groups, prior


def audit_groups(groups, all_ids):
    require(set(groups) == {"train", "validation", "test"}, "missing split")
    require(all(groups.values()), "empty split")
    require(not (groups["train"] & groups["validation"] or groups["train"] & groups["test"] or groups["validation"] & groups["test"]), "run group overlap")
    require(set.union(*groups.values()) == all_ids, "missing or extra run groups")


def snapshot_key(row):
    return (row.run_id, row.timestamp_seconds, row.intersection_id, row.approach_id)


def prepare_data(data_dir=None, output_dir=None, audit_path=None, seed=57, prior_map_path=None):
    data_dir = Path(data_dir or ROOT / "ml-service/data").resolve()
    output_dir = Path(output_dir or data_dir / "splits").resolve()
    require(output_dir != data_dir, "use a split subdirectory, not the source directory")
    inputs = sorted(data_dir.glob("*.csv"))
    before = {path.name: digest(path) for path in inputs}
    fields, rows = read_csv(data_dir / "traffic_observations.csv")
    require(fields == list(LabeledTrafficRecord.model_fields), "labeled CSV columns differ from canonical schema")
    _, metadata = read_csv(data_dir / "run_metadata.csv")
    _, source_rows = read_csv(data_dir / "traffic_source_snapshots.csv")
    audit_feature_lists()
    metadata_ids = {row["run_id"] for row in metadata}
    require(metadata_ids == {row["run_id"] for row in rows}, "metadata/data run mismatch")
    require(len({row["run_seed"] for row in metadata}) == len(metadata), "run seeds are reused: possible duplicate/related rollout")
    for row in metadata:
        provenance = {key: row[key] for key in RunProvenance.model_fields}
        for key in ("seed", "observation_interval_seconds", "prediction_horizon_seconds"):
            provenance[key] = int(provenance[key])
        RunProvenance.model_validate(provenance)
    observed = [TrafficObservation.model_validate(typed(row)) for row in source_rows]
    lookup = {snapshot_key(row): row for row in observed}
    require(len(lookup) == len(observed), "duplicate source snapshot keys")
    require({row.run_id for row in observed} == metadata_ids, "source/data run mismatch")
    labeled = [LabeledTrafficRecord.model_validate(typed(row)) for row in rows]
    require(len({snapshot_key(row) for row in labeled}) == len(labeled), "duplicate labeled snapshot keys")
    by_run = defaultdict(list)
    for raw, row in zip(rows, labeled):
        key = snapshot_key(row)
        require(key in lookup, "current source snapshot missing")
        require(row.model_dump(exclude=TARGETS) == lookup[key].model_dump(), "current fields differ from source")
        future_key = (row.run_id, row.timestamp_seconds + 60, row.intersection_id, row.approach_id)
        require(future_key in lookup, "exact same-group future source snapshot missing")
        require(row.future_wait_seconds == lookup[future_key].mean_wait_seconds, "future target does not match same-group t+60 source")
        by_run[row.run_id].append(raw)
    timelines = defaultdict(list)
    for row in labeled:
        timelines[(row.run_id, row.intersection_id, row.approach_id)].append(row.timestamp_seconds)
    require(all(times == sorted(times) for times in timelines.values()), "non-monotonic run/approach time order")
    trajectories = []
    for run, run_rows in sorted(by_run.items()):
        signature = [[row[name] for name in fields if name != "run_id"] for row in run_rows]
        trajectories.append(hashlib.sha256(json.dumps(signature, separators=(",", ":")).encode()).hexdigest())
    require(len(set(trajectories)) == len(trajectories), "identical trajectories under different run IDs")
    groups, prior = split_groups(metadata, seed)
    # Verify the current notebook's saved split if it exists. Reconstructing the policy
    # makes the resulting membership reproducible even in a fresh clone without artifacts.
    prior_map_path = Path(prior_map_path or ROOT / "artifacts/eda/run_split.csv")
    if prior_map_path.is_file():
        _, old_rows = read_csv(prior_map_path)
        require(len(old_rows) == len(prior), "prior EDA map row count mismatch")
        require({row["run_id"]: row["split"] for row in old_rows} == prior, "prior EDA map disagrees with reconstructed policy; review exposure before splitting")
    prior_train = {run for run, split in prior.items() if split == "train"}
    require(not groups["test"] & prior_train, "final test was previously explored in EDA")
    require(all(sum(run in ids for ids in groups.values()) == 1 for run in metadata_ids), "run appears in multiple splits")
    # A run's complete windows AND future-label sources are bound to the same split.
    assignment = {run: name for name, ids in groups.items() for run in ids}
    require(all(assignment[row.run_id] == assignment[lookup[(row.run_id, row.timestamp_seconds + 60, row.intersection_id, row.approach_id)].run_id] for row in labeled), "look-ahead crosses a split")
    output_dir.mkdir(parents=True, exist_ok=True)
    split_info = {}
    emitted = []
    scenario = {row["run_id"]: row["scenario_type"] for row in metadata}
    for name, ids in groups.items():
        selected = [row for row in rows if row["run_id"] in ids]
        path = output_dir / f"{name}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(selected)
        reloaded_fields, reloaded = read_csv(path)
        require(reloaded_fields == fields and reloaded == selected, f"raw split cells changed: {name}")
        emitted.extend(tuple(row[column] for column in fields) for row in reloaded)
        split_info[name] = {"groups": len(ids), "rows": len(selected), "run_ids": sorted(ids),
                            "group_fraction": len(ids) / len(metadata), "row_fraction": len(selected) / len(rows),
                            "scenario_groups": dict(sorted(Counter(scenario[run] for run in ids).items())),
                            "file": path.name, "sha256": digest(path)}
    require(Counter(emitted) == Counter(tuple(row[column] for column in fields) for row in rows), "split union differs from complete original rows")
    require(before == {path.name: digest(path) for path in inputs}, "source CSV bytes changed")
    manifest = {
        "version": "run-split-v1", "seed": seed, "group_column": "run_id",
        "requested_ratios": {"train": 0.6, "validation": 0.2, "test": 0.2},
        "method": "feature-blind seeded run grouping with historical EDA test protection",
        "input_rows": len(rows), "input_groups": len(metadata), "source_sha256": before,
        "splits": split_info, "features": {"classification": list(CLASSIFICATION_FEATURES), "future_wait_regression": list(REGRESSION_FEATURES)},
        "targets": {"classification": "congestion_level", "future_wait_regression": "future_wait_seconds"},
        "prediction_horizon_seconds": 60,
        "excluded_identifiers": sorted(IDENTIFIERS), "excluded_targets": sorted(TARGETS),
        "classification_excluded_rule_inputs": sorted(RULE_INPUTS),
        "classification_extra_exclusion": {"gps_sample_count": "close proxy for vehicle_count; conservative exclusion"},
        "prior_eda_policy": "per scenario: seed-57 permutation of sorted run IDs, first4=train, next1=validation, remainder=test",
        "prior_eda_training_runs": sorted(prior_train),
        "prior_eda_exposure": {name: sorted(ids & prior_train) for name, ids in groups.items()},
        "checks": {"group_disjointness": True, "all_rows_preserved": True, "source_bytes_unchanged": True, "time_order_preserved": True,
                   "future_labels_exact_same_group": True, "prediction_time_features_only": True,
                   "unique_declared_run_seeds": True, "no_identical_renamed_rollouts": True,
                   "test_not_previously_explored_in_eda": True, "preprocessing_fitted": False},
        "limitations": ["Validation includes previously explored EDA groups; it is a development set, not pristine holdout.",
                        "Congestion remains a deterministic feature-derived synthetic index despite removing its direct rule inputs.",
                        "Regression uses simulator-truth queue/count/wait covariates, not GPS-only observations.",
                        "Unique seeds and trajectory fingerprints are evidence, not a statistical proof of independent realism.",
                        "Legacy EDA artifacts/old notebook retain their historical 20/5/5 split; this manifest is authoritative for training."],
    }
    (output_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if audit_path is not None:
        write_audit(Path(audit_path), manifest, output_dir)
    return manifest


def write_audit(path, manifest, output_dir):
    text = """# Leakage audit

Seed **57**. Synthetic traffic only, never live GPS. No model or preprocessing is fitted.
All syllabus topics remain **UNVERIFIED**. `ml-service/data/splits/split_manifest.json`
is the authoritative training split, superseding the historical EDA 20/5/5 map.

## Persisted raw splits

| Split | Independent runs | Rows | Run share |
| --- | ---: | ---: | ---: |
"""
    for name, info in manifest["splits"].items():
        text += f"| {name} | {info['groups']} | {info['rows']:,} | {100*info['group_fraction']:.1f}% |\n"
    text += f"\nFiles: `{output_dir}`: `train.csv`, `validation.csv`, `test.csv`, `split_manifest.json`. Raw CSVs retain all original columns and targets for audit/storage; **training must select only the approved task feature list**, not every non-target column. Original cell strings, null-speed blanks and row order within each run are preserved.\n"
    text += """
## Historical EDA exposure

The earlier notebook explored 20 runs (four per demand archetype). The seed-57 split
reconstructs that feature-blind policy without inspecting targets, protects never-explored
groups for final test, and verifies the saved EDA map when present. Existing test runs
are preferred, followed by old validation runs. Training groups are selected preferentially
from the previous EDA training pool. No target-dependent balancing or outcome-based choice
is made. No observations within a run are divided, including across approaches.

"""
    exposed = manifest["prior_eda_exposure"]["validation"]
    text += f"Previously explored runs now in validation: **{len(exposed)}** ({', '.join(exposed)}). Validation is an explicitly exposed development set, **not a pristine holdout**. Final test overlap with previous EDA training: **0**. Rerunning EDA cannot undo prior exposure. No model/transform fitting or tuning has occurred. Keep future feature EDA within the new train groups; never treat the old 20-run EDA mask as the current training mask.\n"
    text += """
## Prediction-time features

Classification target: `congestion_level` at t. Approved fields:

"""
    text += ", ".join(f"`{name}`" for name in CLASSIFICATION_FEATURES) + ".\n"
    text += """
Excluded are both targets; run/intersection/approach IDs and raw timestamp; all five
direct congestion rule inputs (speed, reference speed, count, queue, current wait);
and GPS sample count as a conservative close count proxy. Speed ratios, rule scores,
encoded labels, target statistics and other engineered target-derived values are not
approved. The current label remains synthetic rule-derived; indirect correlation through
flows/phase/time can persist, so scores must not be claimed as independent empirical
congestion discovery. The direct rule is an oracle-definition check, not model accuracy.

Regression target: `future_wait_seconds` at exact t+60. Approved fields:

"""
    text += ", ".join(f"`{name}`" for name in REGRESSION_FEATURES) + ".\n"
    text += """
These are current snapshots and counters for the completed (t-10,t] interval. Current
queue/wait/count are simulator truth available at prediction t, not the realized future
outcome; use a current-wait persistence baseline later. This is **not GPS-only sensing**.
`time_of_day` is known synthetic clock information, not a future timestamp. No t+60
row, future phase/action/flow, outcome-derived statistic, full-run aggregate, scenario,
seed or provenance field is an input.

## Assertions and evidence

- Pairwise run intersections are empty; union covers all input runs and every original
  row exactly once. All approaches/neighbors in a run stay together. Overlapping absolute
  synthetic timestamps across different independent runs are expected and are not overlap.
- Canonical Pydantic contracts validate observations, targets and synthetic provenance.
  Declared run seeds are unique; renamed identical whole-run trajectories are rejected.
- Every target uses a matching same-run/intersection/approach t+60 source snapshot;
  source look-ahead inherits the current run split. Tail sources are audit evidence,
  not additional predictors or rows copied into another split.
- Feature allowlists reject IDs, either target, unknown engineered and post-outcome
  columns. Classification additionally rejects its rule-defining inputs and count proxy.
- Split CSV re-read matches original raw cells; split union and source SHA-256 checks
  pass. Null speed is not imputed, no rows dropped or scaled, and no outlier rule learned.
- Imputation, scaling, encoding, PCA/selection and tuning must later be fitted only on
  training groups, inside grouped validation folds. Test is reserved for final evaluation.

Manifest records group assignments, counts, source/output hashes, feature lists and
explicit exposure limits. Group independence follows the synthetic generator design;
it is not proof of realism, causal controller benefit or applicability to physical signals.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "ml-service/data")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--audit-path", type=Path, default=ROOT / "docs/LEAKAGE_AUDIT.md")
    parser.add_argument("--seed", type=int, choices=[57], default=57)
    args = parser.parse_args()
    manifest = prepare_data(args.data_dir, args.output_dir, args.audit_path, args.seed)
    print(json.dumps({"seed": manifest["seed"], "counts": {name: {key: value[key] for key in ("groups", "rows", "group_fraction")} for name, value in manifest["splits"].items()},
                      "output_dir": str(args.output_dir or args.data_dir / "splits"), "audit": str(args.audit_path),
                      "checks": manifest["checks"], "previously_explored_validation_runs": manifest["prior_eda_exposure"]["validation"]}, indent=2))


if __name__ == "__main__":
    main()
