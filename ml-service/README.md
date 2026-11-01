# ML service

FastAPI scaffold only. GET `/health` reports liveness and explicit implementation limits.
No training, prediction, physical signal integration, or private GPS ingestion exists.

From the repository root (PowerShell):

```powershell
.\ml-service\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir ml-service --host 127.0.0.1 --port 8000
```

Python 3.12 is the tested interpreter; install root requirements in a venv.
Dependencies and versions are recorded in `requirements.lock.txt` at the root.
