"""Optional, local SUMO fixed-time smoke adapter. Never imported by the main API.

Only the generated synthetic through-only junction is supported. No TraCI,
remote connections, uploaded configurations, real demand or physical actuation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from simulation.controllers import TimingConfig

STATES = ("GrGr", "yryr", "rrrr", "rGrG", "ryry", "rrrr")
DIRECTIONS = ("N", "E", "S", "W")
OPPOSITE = dict(N="S", E="W", S="N", W="E")


class SumoUnavailable(RuntimeError):
    pass


def discover():
    """Read-only lookup; no subprocess, import side effects or installation."""
    roots = []
    if os.getenv("SUMO_HOME"):
        roots.append(Path(os.environ["SUMO_HOME"]) / "bin")
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.getenv(variable):
            roots.extend(Path(os.environ[variable]) / p / "bin" for p in ("Eclipse/Sumo", "Sumo"))
    found = {}
    for name in ("sumo", "netconvert"):
        path = shutil.which(name)
        if not path:
            path = next((str(root / (name + suffix)) for root in roots
                         for suffix in (".exe", "") if (root / (name + suffix)).is_file()), None)
        found[name] = path
    return found


def require_enabled():
    if os.getenv("RAAH_ENABLE_SUMO") != "1":
        raise SumoUnavailable("SUMO disabled: explicitly set RAAH_ENABLE_SUMO=1")


def execute(command, cwd):
    """Bounded child process, argument vector only; errors remain explicit."""
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                            timeout=60, check=False)
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} exited {result.returncode}: {result.stderr[-4000:]}")
    return {"command": command, "stdout": result.stdout, "stderr": result.stderr,
            "returncode": result.returncode}


def write_xml(path, root):
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def phase_plan():
    timing = TimingConfig()
    durations = (timing.fixed_green, timing.yellow, timing.all_red) * 2
    return tuple(zip(durations, STATES))


def expected_state(second):
    plan = phase_plan()
    remaining = second % sum(duration for duration, _ in plan)
    for duration, state in plan:
        if remaining < duration:
            return state
        remaining -= duration
    raise AssertionError("unreachable phase")


def write_fixture(folder):
    nodes = ET.Element("nodes")
    ET.SubElement(nodes, "node", id="J", x="0", y="0", type="traffic_light")
    edges = ET.Element("edges")
    connections = ET.Element("connections")
    positions = dict(N=(0, 150), E=(150, 0), S=(0, -150), W=(-150, 0))
    for index, direction in enumerate(DIRECTIONS):
        x, y = positions[direction]
        ET.SubElement(nodes, "node", id=direction, x=str(x), y=str(y), type="priority")
        for incoming in (True, False):
            ET.SubElement(edges, "edge", {"id": direction + ("_in" if incoming else "_out"),
                "from": direction if incoming else "J", "to": "J" if incoming else direction,
                "numLanes": "1", "speed": "13.89"})
        ET.SubElement(connections, "connection", {"from": direction + "_in",
            "to": OPPOSITE[direction] + "_out", "fromLane": "0", "toLane": "0",
            "tl": "J", "linkIndex": str(index)})
    lights = ET.Element("tlLogics")
    logic = ET.SubElement(lights, "tlLogic", id="J", type="static", programID="raah", offset="0")
    for duration, state in phase_plan():
        ET.SubElement(logic, "phase", duration=str(duration), state=state)
    routes = ET.Element("routes")
    ET.SubElement(routes, "vType", id="synthetic", sigma="0")
    for index, direction in enumerate(DIRECTIONS):
        ET.SubElement(routes, "route", id=direction, edges=direction + "_in " + OPPOSITE[direction] + "_out")
        ET.SubElement(routes, "flow", id="synthetic_" + direction, type="synthetic", route=direction,
                      begin=str(index), end="120", period="10")
    additional = ET.Element("additional")
    ET.SubElement(additional, "timedEvent", type="SaveTLSStates", source="J", dest="tls_states.xml")
    for name, root in (("nodes.xml", nodes), ("edges.xml", edges), ("connections.xml", connections),
                       ("lights.xml", lights), ("routes.xml", routes), ("additional.xml", additional)):
        write_xml(folder / name, root)


def audit_network(path):
    root = ET.parse(path).getroot()
    actual = {(r.get("from"), r.get("to"), r.get("linkIndex"))
              for r in root.findall("connection") if r.get("tl") == "J"}
    expected = {(d + "_in", OPPOSITE[d] + "_out", str(i)) for i, d in enumerate(DIRECTIONS)}
    programs = root.findall("tlLogic")
    if actual != expected or len(programs) != 1:
        raise ValueError("compiled network has unexpected signal mapping/programs")
    phases = tuple((float(p.get("duration")), p.get("state")) for p in programs[0].findall("phase"))
    if programs[0].get("programID") != "raah" or phases != phase_plan():
        raise ValueError("compiled phase program differs from constrained virtual plan")


def audit_trace(path, seconds=136):
    rows = ET.parse(path).getroot().findall("tlsState")
    if len(rows) != seconds:
        raise ValueError("incomplete SUMO phase trace")
    for second, row in enumerate(rows):
        if (float(row.get("time")) != second or row.get("id") != "J"
                or row.get("state") != expected_state(second)):
            raise ValueError(f"illegal phase or timing at tick {second}")
    return len(rows)


def run_smoke(output):
    require_enabled()  # before lookup, filesystem creation or launching processes
    tools = discover()
    missing = [name for name, path in tools.items() if not path]
    if missing:
        raise SumoUnavailable("SUMO unavailable; missing executables: " + ", ".join(missing))
    folder = Path(output).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    if any(folder.iterdir()):
        raise ValueError("use a fresh empty SUMO output directory; existing work is preserved")
    logs = [execute([path, "--version"], folder) for path in tools.values()]
    write_fixture(folder)
    logs.append(execute([tools["netconvert"], "--node-files", "nodes.xml", "--edge-files", "edges.xml",
                         "--connection-files", "connections.xml", "--tllogic-files", "lights.xml",
                         "--output-file", "junction.net.xml"], folder))
    audit_network(folder / "junction.net.xml")
    logs.append(execute([tools["sumo"], "--net-file", "junction.net.xml", "--route-files", "routes.xml",
        "--additional-files", "additional.xml", "--seed", "57", "--step-length", "1", "--begin", "0",
        "--end", "136", "--no-step-log", "true", "--tripinfo-output", "tripinfo.xml"], folder))
    ticks = audit_trace(folder / "tls_states.xml")
    trips = len(ET.parse(folder / "tripinfo.xml").getroot().findall("tripinfo"))
    if trips == 0:
        raise ValueError("SUMO completed no synthetic trips")
    report = dict(status="working", seed=57, synthetic_only=True, virtual_only=True,
                  ticks=ticks, completed_trips=trips, commands=logs,
                  limitation="fixed-time smoke only; not an ML/controller performance validation")
    (folder / "smoke_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="read-only executable lookup")
    parser.add_argument("--output", default="artifacts/sumo/smoke")
    args = parser.parse_args()
    if args.status:
        tools = discover()
        print(json.dumps(dict(enabled=os.getenv("RAAH_ENABLE_SUMO") == "1", tools=tools,
                              available=all(tools.values())), indent=2))
        return 0
    try:
        print(json.dumps(run_smoke(args.output), indent=2))
        return 0
    except SumoUnavailable as exc:
        print(json.dumps(dict(status="skipped", reason=str(exc))))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
