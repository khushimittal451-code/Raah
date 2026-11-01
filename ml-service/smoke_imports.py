"""Print actual versions of the requested importable dependencies."""
import importlib
import importlib.metadata
import json
import platform
import os
from pathlib import Path

# Use a project-local headless plotting cache during import checks.
cache = Path(__file__).resolve().parents[1] / "work" / "matplotlib"
cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache))
os.environ.setdefault("MPLBACKEND", "Agg")

packages = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "pandas": "pandas",
    "numpy": "numpy",
    "sklearn": "scikit-learn",
    "joblib": "joblib",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "pytest": "pytest",
    "httpx": "httpx",
}
versions = {"python": platform.python_version()}
for module, distribution in packages.items():
    importlib.import_module(module)
    versions[distribution] = importlib.metadata.version(distribution)
print(json.dumps(versions, indent=2))
