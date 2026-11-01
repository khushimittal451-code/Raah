"""Read-only hash-checked inference bundle; never fits or evaluates models."""
import hashlib
import json
from pathlib import Path
from threading import Lock
import joblib
import numpy as np
import pandas as pd
from training.prepare_data import CLASSIFICATION_FEATURES, REGRESSION_FEATURES

FEATURES = {'classification': list(CLASSIFICATION_FEATURES), 'regression': list(REGRESSION_FEATURES)}
ROOT = Path(__file__).resolve().parents[2]

class Unavailable(Exception):
    pass

class ModelBundle:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.version = None
        self.models = {}
        self.info = {task: {'available': False, 'input_features': features, 'error': 'not_loaded'} for task, features in FEATURES.items()}
        self.locks = {task: Lock() for task in FEATURES}

    def load(self):
        self.models.clear()
        try:
            raw = (self.directory / 'selection_manifest.json').read_bytes()
            manifest = json.loads(raw)
            schema = json.loads((self.directory / 'feature_schema.json').read_text(encoding='utf-8'))
            if schema['version'] != 'final-feature-schema-v1':
                raise ValueError('unsupported feature schema version')
            self.version = hashlib.sha256(raw).hexdigest()
        except Exception as exc:
            for state in self.info.values():
                state.update(available=False, error=f'bundle_metadata_unavailable: {type(exc).__name__}')
            return
        for task, features in FEATURES.items():
            state = self.info[task]
            state.update(available=False)
            try:
                contract = schema['tasks'][task]
                if ([item['name'] for item in contract['input_features']] != features
                        or manifest['feature_lists'][task] != features
                        or manifest['choices'][task]['model'] != contract['model']):
                    raise ValueError('feature or selected model contract mismatch')
                filename = contract['pipeline_file']
                if filename != f'{task}_pipeline.joblib':
                    raise ValueError('unexpected pipeline filename')
                path = self.directory / filename
                if hashlib.sha256(path.read_bytes()).hexdigest() != contract['pipeline_sha256']:
                    raise ValueError('pipeline hash mismatch')
                # Trusted local artifacts only; joblib uploads are never accepted.
                model = joblib.load(path)
                if list(model[:-1].get_feature_names_out()) != contract['transformed_feature_order']:
                    raise ValueError('transformed feature contract mismatch')
                if list(model.feature_names_in_) != features:
                    raise ValueError('pipeline input order mismatch')
                self.models[task] = model
                state.update(available=True, error=None, model=contract['model'], pipeline_sha256=contract['pipeline_sha256'])
            except Exception as exc:
                state.update(error=f'model_artifact_unavailable: {type(exc).__name__}: {exc}')

    def require(self, tasks):
        for task in tasks:
            if task not in self.models:
                raise Unavailable(f"{task}: {self.info[task]['error']}")

    def predict(self, task, observations):
        self.require([task])
        frame = pd.DataFrame([row.model_dump() for row in observations], columns=FEATURES[task])
        try:
            with self.locks[task]:
                values = np.asarray(self.models[task].predict(frame))
            if values.shape != (len(observations),):
                raise ValueError('unexpected prediction shape')
            if task == 'classification':
                if not set(values.tolist()) <= {'LOW', 'MEDIUM', 'HIGH'}:
                    raise ValueError('unexpected class label')
            elif not np.isfinite(values.astype(float)).all():
                raise ValueError('nonfinite prediction')
            return values.tolist()
        except Exception as exc:
            raise Unavailable(f'{task}: inference_failed: {type(exc).__name__}') from exc

    def describe(self):
        return {'model_version': self.version, 'status': 'PROVISIONAL_UNVERIFIED', 'data_mode': 'synthetic-only',
                'prediction_horizon_seconds': 60, 'tasks': self.info}
