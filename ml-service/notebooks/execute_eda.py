"""Execute 01_eda.ipynb with Jupyter if available, otherwise transparent Python fallback.

No installation, data regeneration or model fitting is performed. The fallback runs plain
Python cells in one shared namespace, captures stdout/PNG output and checks input hashes;
it does not pretend to be a Jupyter kernel or official nbformat validation.
"""
import ast
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "ml-service/notebooks/01_eda.ipynb"
ARTIFACTS = ROOT / "artifacts/eda"


def input_hashes():
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "ml-service/data").glob("*.csv"))}


def main():
    os.chdir(ROOT)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    before = input_hashes()
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4 and notebook["nbformat_minor"] == 5
    assert len({cell["id"] for cell in notebook["cells"]}) == len(notebook["cells"])
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    for cell in code_cells:
        source = cell["source"]
        if isinstance(source, list):
            source = "".join(source)
            cell["source"] = source
        ast.parse(source)
        cell["execution_count"], cell["outputs"] = None, []
    modules = {name: importlib.util.find_spec(name) is not None
               for name in ("nbformat", "nbclient", "jupyter_client", "ipykernel")}
    print("Jupyter tooling:", json.dumps(modules), flush=True)
    mode = "jupyter-nbclient" if all(modules.values()) else "python-sequential-fallback"
    print("Execution mode:", mode, flush=True)
    start = time.perf_counter()
    caught_error = None
    try:
        if mode == "jupyter-nbclient":
            # A local temporary kernelspec ensures the kernel uses this exact venv.
            jupyter_home = ROOT / "work/eda/jupyter-data"
            kernel_dir = jupyter_home / "kernels/raah-service"
            kernel_dir.mkdir(parents=True, exist_ok=True)
            (kernel_dir / "kernel.json").write_text(json.dumps({
                "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                "display_name": "Raah service Python", "language": "python",
            }), encoding="utf-8")
            os.environ["JUPYTER_PATH"] = str(jupyter_home) + os.pathsep + os.environ.get("JUPYTER_PATH", "")
            os.environ["JUPYTER_RUNTIME_DIR"] = str(ROOT / "work/eda/jupyter-runtime")
            os.environ["IPYTHONDIR"] = str(ROOT / "work/eda/ipython")
            import nbformat
            from nbclient import NotebookClient
            nb = nbformat.from_dict(notebook)
            nbformat.validate(nb)
            NotebookClient(nb, timeout=180, kernel_name="raah-service",
                           resources={"metadata": {"path": str(NOTEBOOK.parent)}}).execute()
            notebook = dict(nb)
            code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
            nbformat.validate(nb)
        else:
            namespace = {"__name__": "__main__"}
            for count, cell in enumerate(code_cells, 1):
                stdout, stderr = io.StringIO(), io.StringIO()
                offsets = {"stdout": 0, "stderr": 0}

                def flush_streams():
                    for name, stream in (("stdout", stdout), ("stderr", stderr)):
                        content = stream.getvalue()[offsets[name]:]
                        if content:
                            cell["outputs"].append({"output_type": "stream", "name": name, "text": content})
                            offsets[name] = len(stream.getvalue())

                def emit_png(path):
                    flush_streams()
                    cell["outputs"].append({"output_type": "display_data", "metadata": {}, "data": {
                        "image/png": base64.b64encode(path.read_bytes()).decode("ascii"),
                        "text/plain": f"Chart: {path.name}",
                    }})

                namespace["_raah_emit_png"] = emit_png
                cell["execution_count"] = count
                try:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        exec(compile(cell["source"], f"01_eda.ipynb:cell-{count}", "exec"), namespace)
                except Exception as exc:
                    flush_streams()
                    cell["outputs"].append({"output_type": "error", "ename": type(exc).__name__,
                                            "evalue": str(exc), "traceback": traceback.format_exc().splitlines()})
                    raise
                flush_streams()
                print(f"Cell {count}/{len(code_cells)}: PASS", flush=True)
    except Exception:
        caught_error = traceback.format_exc()
    after = input_hashes()
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    errors = [output for cell in code_cells for output in cell["outputs"] if output["output_type"] == "error"]
    images = [output for cell in code_cells for output in cell["outputs"] if "image/png" in output.get("data", {})]
    executed = sum(isinstance(cell["execution_count"], int) for cell in code_cells)
    pngs = sorted(ARTIFACTS.glob("[0-9][0-9]_*.png"))
    checks = {
        "all_code_cells_executed": executed == len(code_cells),
        "no_cell_errors": not errors and caught_error is None,
        "nine_embedded_charts": len(images) == 9,
        "nine_saved_charts": len(pngs) == 9,
        "valid_png_signatures": all(p.read_bytes().startswith(bytes.fromhex("89504e470d0a1a0a")) for p in pngs),
        "all_input_csv_hashes_unchanged": before == after,
    }
    result = {"mode": mode, "jupyter_tooling": modules, "code_cells": len(code_cells),
              "executed_code_cells": executed, "cell_errors": len(errors), "embedded_charts": len(images),
              "checks": checks, "elapsed_seconds": round(time.perf_counter() - start, 3),
              "error": caught_error, "official_nbformat_validation": mode == "jupyter-nbclient"}
    notebook["metadata"]["raah_execution"] = result
    NOTEBOOK.write_text(json.dumps(notebook, indent=2) + "\n", encoding="utf-8")
    (ARTIFACTS / "execution_check.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    findings = ROOT / "docs/EDA_FINDINGS.md"
    if not findings.exists():
        findings.write_text("# EDA findings\n\nNotebook execution failed before findings could be generated.\n", encoding="utf-8")
    with findings.open("a", encoding="utf-8") as handle:
        handle.write("\n## Execution checks\n\n")
        handle.write("Command: `.\\ml-service\\.venv\\Scripts\\python.exe ml-service/notebooks/execute_eda.py`.\n\n")
        handle.write("Jupyter tooling is unavailable in this environment; conventional kernel execution and official nbformat validation were skipped. Plain-Python fallback executes cells in order and captures real outputs; it does not test kernel behavior.\n\n" if mode != "jupyter-nbclient" else "Executed with nbclient using the service venv kernel and validated with nbformat.\n\n")
        handle.write("```json\n" + json.dumps(result, indent=2) + "\n```\n")
        handle.write("\nNo packages installed and no raw input files changed. No model was trained. Charts are derived artifacts.\n")
    print(json.dumps(result, indent=2), flush=True)
    if caught_error:
        print(caught_error, file=sys.stderr)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
