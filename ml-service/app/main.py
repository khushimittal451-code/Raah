"""Synthetic-only inference API using frozen local model artifacts."""
from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import Field
from app.models import ModelBundle, ROOT, Unavailable
from app.schemas import StrictRecord, TrafficObservation

class BatchRequest(StrictRecord):
    observations: list[TrafficObservation] = Field(min_length=1, max_length=100)

def create_app(model_dir: Path | None = None):
    @asynccontextmanager
    async def lifespan(application):
        application.state.bundle = ModelBundle(model_dir or os.getenv('RAAH_MODEL_DIR', str(ROOT / 'artifacts/final')))
        application.state.bundle.load()
        yield

    application = FastAPI(title='Raah ML Service', version='0.2.0', lifespan=lifespan)
    origins = [value.strip() for value in os.getenv('RAAH_CORS_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',') if value.strip()]
    application.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                               allow_methods=['GET', 'POST'], allow_headers=['Accept', 'Content-Type'])

    @application.exception_handler(Unavailable)
    async def unavailable(_request, exc):
        return JSONResponse(status_code=503, content={'detail': {'code': 'model_unavailable', 'reason': str(exc)}})

    def bundle(request):
        loaded = getattr(request.app.state, 'bundle', None)
        if loaded is None:
            raise Unavailable('startup has not loaded model artifacts')
        return loaded

    def wait_result(value):
        # Raw polynomial outputs are preserved; negative waits are explicitly flagged.
        return {'future_wait_seconds': value, 'prediction_horizon_seconds': 60,
                'nonphysical_wait': value < 0, 'warning': 'negative_model_output' if value < 0 else None}

    @application.get('/health')
    def health():
        """Liveness only; /model-info reports model readiness."""
        return {'status': 'ok', 'service': 'raah-ml-service', 'seed': 57,
                'data_mode': 'synthetic-only', 'controller': 'not-implemented', 'syllabus': 'UNVERIFIED'}

    @application.get('/model-info')
    def model_info(request: Request):
        return bundle(request).describe()

    @application.post('/predict/congestion')
    def congestion(observation: TrafficObservation, request: Request):
        loaded = bundle(request)
        value = loaded.predict('classification', [observation])[0]
        return {'model_version': loaded.version, 'congestion_level': value}

    @application.post('/predict/wait')
    def wait(observation: TrafficObservation, request: Request):
        loaded = bundle(request)
        value = loaded.predict('regression', [observation])[0]
        return {'model_version': loaded.version, **wait_result(value)}

    @application.post('/predict/batch')
    def batch(body: BatchRequest, request: Request):
        loaded = bundle(request)
        loaded.require(['classification', 'regression'])
        classes = loaded.predict('classification', body.observations)
        waits = loaded.predict('regression', body.observations)
        return {'model_version': loaded.version, 'predictions': [
            {'index': index, 'congestion_level': level, **wait_result(seconds)}
            for index, (level, seconds) in enumerate(zip(classes, waits))]}

    return application

app = create_app()
