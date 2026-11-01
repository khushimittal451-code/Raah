"""Verify live API and Vite proxy, always cleaning up child processes."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import httpx

root = Path.cwd()
(root / "work" / "phase1").mkdir(parents=True, exist_ok=True)
processes = []
logs = []

def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

def launch(command, log_name, env=None):
    print("START", subprocess.list2cmdline(command), flush=True)
    handle = (root / "work" / "phase1" / log_name).open("w", encoding="utf-8")
    logs.append(handle)
    process = subprocess.Popen(command, cwd=root, env=env, stdout=handle,
                               stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    processes.append(process)
    return process

def wait_for(client, url, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError(f"Server exited early: {process.returncode}")
        try:
            response = client.get(url)
            if response.status_code == 200:
                return response
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Server readiness timed out: {url}")

api_port, client_port = free_port(), free_port()
while client_port == api_port:
    client_port = free_port()
try:
    api_url = f"http://127.0.0.1:{api_port}"
    api = launch([sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", "ml-service",
                  "--host", "127.0.0.1", "--port", str(api_port)], "api-server.log")
    with httpx.Client(timeout=2, trust_env=False) as client:
        response = wait_for(client, api_url + "/health", api)
        assert response.json()["status"] == "ok"
        assert response.json()["seed"] == 57
        print("GET /health", response.status_code, json.dumps(response.json()), flush=True)
        env = os.environ.copy()
        env["RAAH_API_TARGET"] = api_url
        vite = launch([shutil.which("node"), "client/node_modules/vite/bin/vite.js", "client",
                       "--host", "127.0.0.1", "--port", str(client_port), "--strictPort"],
                      "vite-server.log", env=env)
        frontend_url = f"http://127.0.0.1:{client_port}"
        page = wait_for(client, frontend_url, vite)
        assert '<div id="root"></div>' in page.text
        print("GET frontend /", page.status_code, "React entry HTML verified", flush=True)
        proxy = client.get(frontend_url + "/api/health")
        assert proxy.status_code == 200 and proxy.json() == response.json()
        print("GET frontend /api/health", proxy.status_code, "Vite proxy matches API", flush=True)
finally:
    for process in reversed(processes):
        if os.name == "nt" and process.poll() is None:
            # Windows venv launchers can have a child interpreter: stop the tree.
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0 and process.poll() is None:
                process.terminate()
        elif process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        print("STOPPED", process.pid, "exit", process.returncode, flush=True)
    for handle in logs:
        handle.close()
    for port in (api_port, client_port):
        for _ in range(30):
            with socket.socket() as sock:
                sock.settimeout(0.2)
                closed = sock.connect_ex(("127.0.0.1", port)) != 0
            if closed:
                break
            time.sleep(0.1)
        assert closed, f"Port {port} still listening"
    print("PASS: temporary servers stopped; both ports closed", flush=True)
