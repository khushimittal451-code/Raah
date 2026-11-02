"""Check real Git exclusion behavior without creating secret/sensitive files."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_sensitive_data_and_secrets_are_ignored_at_project_depths():
    git = shutil.which('git')
    if git is None or not (ROOT / '.git').exists():
        pytest.skip('Git checkout unavailable for exclusion integration check')
    protected = [
        '.env', '.env.local', 'ml-service/.env', 'client/.env.production',
        'data/raw/gps.csv', 'data/private/gps.csv', 'data/sensitive/gps.csv',
        'ml-service/data/raw/gps.csv', 'ml-service/data/private/gps.csv',
        'ml-service/data/sensitive/gps.csv', 'nested/raw_sensitive_data/gps.csv',
        'ml-service/.venv/cache.txt', 'client/node_modules/cache.js',
        'client/dist/index.html', 'artifacts/model.joblib', 'nested/private.key',
    ]
    public = ['.env.example', 'ml-service/data/traffic_observations.csv', 'requirements.txt']
    result = subprocess.run([git, 'check-ignore', '--no-index', '-z', '--stdin'], cwd=ROOT,
        input=('\0'.join(protected + public) + '\0').encode(), capture_output=True, check=False)
    assert result.returncode in (0, 1), result.stderr.decode(errors='replace')
    ignored = set(result.stdout.decode().split('\0'))
    assert set(protected) <= ignored, f'Unprotected sensitive paths: {set(protected) - ignored}'
    assert not set(public) & ignored, 'Public configuration/synthetic data must remain reviewable'
