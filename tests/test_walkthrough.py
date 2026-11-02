import copy
import json

import pytest

from app.models import Unavailable
from simulation.walkthrough import verify, verify_pair
from test_simulation_api import SyntheticModels


def test_pair_replays_same_arrivals_and_reports_explicit_fallback(tmp_path):
    result=verify(tmp_path/'run',True,SyntheticModels(negative_at=0))
    assert result['identical_arrivals'] and result['heldout_evaluation_executed'] is False
    assert result['fixed']['arrivals']==result['ml']['arrivals']
    assert result['ml']['effective_policy_ticks']=={'rule_only':60}
    assert result['fixed']['constraint_violations']==result['ml']['constraint_violations']==0
    saved=json.loads((tmp_path/'run/receipt.json').read_text(encoding='utf-8'))
    assert saved==result
    with pytest.raises(ValueError,match='fresh empty'):
        verify(tmp_path/'run',True,SyntheticModels())


def test_no_implicit_ml_fallback_or_receipt_on_failure(tmp_path):
    with pytest.raises(Unavailable):
        verify(tmp_path/'run',False,SyntheticModels(negative_at=0))
    assert not (tmp_path/'run').exists()


def test_changed_arrival_trace_fails_comparison(tmp_path):
    result=verify(tmp_path/'run',False,SyntheticModels())
    changed=copy.deepcopy(result['ml'])
    changed['arrivals'][0][0]+=1
    with pytest.raises(AssertionError,match='arrivals'):
        verify_pair(result['fixed'],changed)
