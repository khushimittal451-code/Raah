"""Read saved aggregate metrics only; never evaluate or open held-out observations."""
import csv
import hashlib
import json
import math

from fastapi import APIRouter, HTTPException, Request

router=APIRouter(tags=['dashboard'])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_metrics(bundle):
    folder=bundle.directory
    selection=json.loads((folder/'selection_manifest.json').read_text(encoding='utf-8'))
    frozen=json.loads((folder/'feature_schema.json').read_text(encoding='utf-8'))
    raw_metrics=(folder/'metrics.json').read_bytes()
    data=json.loads(raw_metrics,parse_constant=lambda v: (_ for _ in ()).throw(ValueError('nonfinite metric')))
    version=sha(folder/'selection_manifest.json')
    if data['selection_sha256']!=version or version!=bundle.version or data['evaluation_split']!='test':
        raise ValueError('saved metrics version/split mismatch')
    if any(data['pipeline_hashes'][task]!=frozen['tasks'][task]['pipeline_sha256'] for task in ('classification','regression')):
        raise ValueError('saved pipeline hashes mismatch')
    # Reuse the completed evaluation receipt; never reread data or recompute scores.
    receipt=json.loads((folder/'test_access_claim.json').read_text(encoding='utf-8'))
    if (receipt.get('status')!='COMPLETE' or receipt.get('selection_sha256')!=version
            or any(type(receipt.get(key)) is not int or receipt[key]!=1 for key in
                   ('test_csv_reads','classification_predict_batches','regression_predict_batches'))):
        raise ValueError('saved metrics receipt is incomplete or inconsistent')
    if hashlib.sha256(raw_metrics).hexdigest()!=receipt.get('metrics_sha256'):
        raise ValueError('saved metrics hash differs from completed receipt')
    comparisons={}
    columns={
        'classification':('validation_accuracy','validation_macro_f1','medium_recall','single_row_median_ms'),
        'regression':('validation_mae_seconds','validation_rmse_seconds','validation_r2','negative_predictions')}
    for task,file in [('classification','model_comparison.csv'),('regression','regression_comparison.csv')]:
        try:
            path=folder.parent/task/file
            if sha(path)!=selection['comparison_hashes'][task]:raise ValueError('validation comparison hash mismatch')
            rows=[]
            with path.open(encoding='utf-8',newline='') as handle:
                for row in csv.DictReader(handle):
                    if row['evaluation_split']!='validation':raise ValueError('comparison split mismatch')
                    item=dict(model=row['model'],status=row['status'],evaluation_split='validation')
                    for key in columns[task]:
                        value=float(row[key])
                        if not math.isfinite(value):raise ValueError('nonfinite comparison')
                        item[key]=value
                    rows.append(item)
            comparisons[task]=dict(available=True,rows=rows)
        except (OSError,ValueError,KeyError) as exc:
            comparisons[task]=dict(available=False,reason=str(exc),rows=None)
    return dict(schema_version='dashboard-metrics-v1',model_version=version,status=data['status'],
        seed=data['seed'],evaluation_split='test',evaluated_utc=data['evaluated_utc'],test_rows=data['test_rows'],
        classification=data['classification'],regression=data['regression'],comparisons=comparisons,
        provenance='Saved aggregate metrics; no evaluation was executed',
        limitations=['Synthetic rule-derived labels','Weak MEDIUM recall','Raw regression can be negative','Syllabus UNVERIFIED'])


@router.get('/model-metrics')
def model_metrics(request:Request):
    try:
        return load_metrics(request.app.state.bundle)
    except (OSError,ValueError,KeyError,AttributeError,TypeError) as exc:
        raise HTTPException(503,detail=dict(code='metrics_unavailable',reason=str(exc))) from exc
