import xml.etree.ElementTree as ET

import pytest

from simulation import sumo_adapter as adapter


def test_disabled_has_no_side_effects(monkeypatch, tmp_path):
    monkeypatch.delenv("RAAH_ENABLE_SUMO", raising=False)
    monkeypatch.setattr(adapter, "discover", lambda: pytest.fail("disabled must not discover"))
    with pytest.raises(adapter.SumoUnavailable, match="disabled"):
        adapter.run_smoke(tmp_path / "unused")
    assert not (tmp_path / "unused").exists()


def test_missing_tools_fail_explicitly(monkeypatch, tmp_path):
    monkeypatch.setenv("RAAH_ENABLE_SUMO", "1")
    monkeypatch.setattr(adapter, "discover", lambda: dict(sumo=None, netconvert=None))
    with pytest.raises(adapter.SumoUnavailable, match="sumo, netconvert"):
        adapter.run_smoke(tmp_path / "unused")
    assert not (tmp_path / "unused").exists()


def test_virtual_plan_and_trace_reject_timing_or_conflicts(tmp_path):
    adapter.write_fixture(tmp_path)
    root = ET.Element("tlsStates")
    for second in range(136):
        state = adapter.expected_state(second)
        assert not (state[0] == "G" and state[1] == "G")
        ET.SubElement(root, "tlsState", time=str(second), id="J", state=state)
    path = tmp_path / "trace.xml"
    adapter.write_xml(path, root)
    assert adapter.audit_trace(path) == 136
    assert adapter.expected_state(30) == "yryr"
    assert adapter.expected_state(33) == "rrrr"
    assert adapter.expected_state(34) == "rGrG"
    root[34].set("state", "GGGG")
    adapter.write_xml(path, root)
    with pytest.raises(ValueError, match="illegal"):
        adapter.audit_trace(path)
    root.remove(root[-1])
    adapter.write_xml(path, root)
    with pytest.raises(ValueError, match="incomplete"):
        adapter.audit_trace(path)


def test_compiled_network_mapping_is_audited(tmp_path):
    root = ET.Element("net")
    for i, d in enumerate(adapter.DIRECTIONS):
        ET.SubElement(root, "connection", {"from": d + "_in", "to": adapter.OPPOSITE[d] + "_out",
                                          "tl": "J", "linkIndex": str(i)})
    logic = ET.SubElement(root, "tlLogic", programID="raah")
    for duration, state in adapter.phase_plan():
        ET.SubElement(logic, "phase", duration=str(duration), state=state)
    path = tmp_path / "net.xml"
    adapter.write_xml(path, root)
    adapter.audit_network(path)
    root[0].set("linkIndex", "1")
    adapter.write_xml(path, root)
    with pytest.raises(ValueError, match="mapping"):
        adapter.audit_network(path)


def test_preserve_existing_output(monkeypatch, tmp_path):
    monkeypatch.setenv("RAAH_ENABLE_SUMO", "1")
    monkeypatch.setattr(adapter, "discover", lambda: dict(sumo="unused", netconvert="unused"))
    (tmp_path / "keep.txt").write_text("existing work")
    with pytest.raises(ValueError, match="fresh empty"):
        adapter.run_smoke(tmp_path)
    assert (tmp_path / "keep.txt").read_text() == "existing work"


def test_sumo_runtime_smoke_when_installed(monkeypatch, tmp_path):
    tools = adapter.discover()
    missing = [name for name, path in tools.items() if not path]
    if missing:
        pytest.skip("SUMO runtime unavailable: " + ", ".join(missing))
    # Explicit opt-in in this test only; main simulator's environment is unchanged.
    monkeypatch.setenv("RAAH_ENABLE_SUMO", "1")
    result = adapter.run_smoke(tmp_path / "run")
    assert result["status"] == "working" and result["seed"] == 57
    assert result["ticks"] == 136 and result["completed_trips"] > 0
