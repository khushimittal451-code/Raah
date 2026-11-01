"""Export the canonical Pydantic structural contract as JSON Schema Draft 2020-12."""
import json
from pathlib import Path

from pydantic.json_schema import models_json_schema

from app.schemas import LabeledRun, LabeledTrafficRecord, RunProvenance, TrafficObservation


def build_schema():
    _, schema = models_json_schema([
        (TrafficObservation, "validation"),
        (LabeledTrafficRecord, "validation"),
        (RunProvenance, "validation"),
        (LabeledRun, "validation"),
    ])
    schema.update({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:raah:synthetic-traffic:1.0.0",
        "$ref": "#/$defs/LabeledRun",
        "title": "Raah synthetic traffic run, schema 1.0.0",
        "description": "Primary document: provenance plus labeled records. Use $defs/TrafficObservation for inference snapshots. Cross-field and temporal validation requires app.schemas; see docs/DATA_DICTIONARY.md.",
        "x-raah-contract": {
            "seed": 57,
            "observation_interval_seconds": 10,
            "prediction_horizon_seconds": 60,
            "label_rule_version": "congestion-v1",
            "data_source": "synthetic-only",
            "runtime_validators_required": True,
        },
    })
    return schema


if __name__ == "__main__":
    path = Path(__file__).parent / "data" / "schema.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_schema(), indent=2) + "\n", encoding="utf-8")
    print(f"Exported {path}")
