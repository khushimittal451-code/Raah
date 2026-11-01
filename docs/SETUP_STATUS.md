# Raah setup status

Checked: 2026-11-01 (Asia/Calcutta).

## Workspace

Local root: `C:\Users\Hrishit Vats\Documents\Codex\2026-11-01\github-plugin-github-openai-curated-remote`.
Initially contained only empty `work/` and `outputs/` directories. No source, manifests, lockfiles, AGENTS.md, or existing Git repository was found. Existing directories were preserved. Initialized a local Git repository on `main`; no commits or remote configured. This folder is not a checkout containing application code.

The earlier GitHub inspection of `khushimittal451-code/Raah` found an empty repository, no open PRs/issues, and no Actions runs.

## Installed tools

| Tool | Result |
| --- | --- |
| OS | Microsoft Windows 10.0.26200 (reported by .NET) |
| Python | 3.15.0a7, prerelease |
| Python path | `C:\Users\Hrishit Vats\AppData\Local\Programs\Python\Python315\python.exe` |
| Python launcher | `py.exe` exists, but `py -0p` reports no installed Pythons |
| Node | v24.22.1, supplied by the Codex runtime |
| npm | Not found on PATH; Node executable directory contains only node.exe |
| Git | 2.53.0.windows.3, supplied by the Codex runtime |
| venv | `.venv`, verified isolated from base Python |
| pip in venv | 26.0.1 |
| rg | Not found on PATH; PowerShell recursive inventory used |

## Setup performed

- Inspected folder and manifests before installing anything.
- Initialized Git using `git init -b main`.
- Created `.venv` using the available Python. Only bundled pip was bootstrapped; no project packages or network downloads were installed.
- Verified venv Python, isolation, pip version, and installed package list (pip only).
- Added ignore rules for the venv, scratch directory, and generated output copies.
- No privileged install, login, browser authorization, push, or GitHub mutation performed.

## Blockers and dependencies

1. No source or dependency manifests exist. Required Python/Node versions and application dependencies cannot be determined. There are no project dependencies to install, version-check, build, or test.
2. npm is unavailable. This blocks npm-based installation if Raah later supplies a package.json. No global npm installation was attempted without an established project requirement.
3. Available Python is a prerelease. Compatibility with future dependencies remains unverified until Python requirements are supplied.
4. Initial venv creation and explicit ensurepip retry failed with PermissionError in the sandbox default temporary directory. Resolved by setting TEMP and TMP to the workspace `work/tmp` for the successful command process; no global environment changes made.

## Executed commands and results

Commands were run in PowerShell from the workspace root. Grouped below in execution order; diagnostic failures did not stop subsequent inspection.

```powershell
Get-Location
Get-ChildItem -Force
Get-Command python,py,node,npm,git -ErrorAction SilentlyContinue | Select-Object Name,Source
python --version
node --version
npm --version
git --version
[System.Runtime.InteropServices.RuntimeInformation]::OSDescription
git rev-parse --show-toplevel
```

Results: versions above; npm command unavailable; Git reported this was not a repository.

```powershell
rg --files --hidden -g '!.git/**' -g '!outputs/**'
Get-ChildItem -Force -Recurse work,outputs | Select-Object FullName,Length
Get-ChildItem 'C:/Users/Hrishit Vats/Documents/Codex/AGENTS.md','C:/Users/Hrishit Vats/Documents/AGENTS.md','C:/Users/Hrishit Vats/AGENTS.md' -ErrorAction SilentlyContinue | ForEach-Object { Get-Content -LiteralPath $_.FullName }
py -0p
$nodeDir = Split-Path (Get-Command node).Source
Get-ChildItem -LiteralPath $nodeDir -Force | Select-Object Name
Get-Command rg -ErrorAction SilentlyContinue | Select-Object Source
```

Results: no files or ancestor instruction files found; launcher found no registered Python; Node directory contained only node.exe; rg unavailable.

```powershell
git init -b main
python -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m ensurepip --upgrade --default-pip
.\.venv\Scripts\python.exe -m pip --version
git status --short --branch
```

Results: Git initialized successfully, no commits on main; Python executable created, but ensurepip failed on temporary directory permissions; pip initially missing.

```powershell
New-Item -ItemType Directory -Force work/tmp | Out-Null
$env:TEMP = (Resolve-Path work/tmp).Path
$env:TMP = $env:TEMP
python -m venv .venv
.\.venv\Scripts\python.exe -m pip --version
.\.venv\Scripts\python.exe -m pip list --format=json
.\.venv\Scripts\python.exe -c "import sys; print('venv active:', sys.prefix != sys.base_prefix); print('executable:', sys.executable)"
```

Results: success; pip 26.0.1 only; venv active True. Report and .gitignore written using apply_patch. Report copied to outputs for download, then Git status and ignore rules checked.

## Single next action

Provide Raah's existing source/manifests, or define what the application should do so its initial stack and manifests can be created. No interactive setup step is currently required.

## Update: local npm installation (2026-11-01)

This update supersedes the earlier npm-missing blocker. npm and npx 12.2.1 are now installed locally under `work/tools/npm/package`. Use `.\npm.cmd` and `.\npx.cmd` from the workspace root. They use Node from PATH; no global PATH or administrator changes were made. The ignored work directory contains the installation, so these launchers require local setup again in a fresh checkout.

Downloaded metadata from https://registry.npmjs.org/npm/latest and its declared distribution archive. Verified archive SHA-512 against registry integrity before extraction. Registry metadata is saved in work/tools/npm-metadata.json. No application packages were installed because the repository still has no source or manifests.

Commands executed for this update:

```powershell
Get-ChildItem -Force | Select-Object Name,Mode
Get-ChildItem -Recurse -File -Force -Exclude *.pyc | Where-Object { $_.FullName -notmatch '\\(\.venv|\.git|work|outputs)\\' } | Select-Object FullName
Get-Command node,npm,npm.cmd -ErrorAction SilentlyContinue | Select-Object Name,Source
$nodeDir = Split-Path (Get-Command node).Source
Get-ChildItem -LiteralPath (Split-Path $nodeDir) -Force | Select-Object Name
Get-Content docs/SETUP_STATUS.md
$nodeRoot = Split-Path (Split-Path (Get-Command node).Source)
Get-ChildItem -LiteralPath (Join-Path $nodeRoot 'node_modules') -Force | Select-Object -ExpandProperty Name
Get-ChildItem -LiteralPath (Join-Path $nodeRoot 'node_modules/npm') -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
Test-Path (Join-Path $nodeRoot 'node_modules/npm/bin/npm-cli.js')
$ErrorActionPreference = 'Stop'
Get-Command tar | Select-Object Name,Source
New-Item -ItemType Directory -Force work/tools/npm | Out-Null
$npmMeta = Invoke-RestMethod 'https://registry.npmjs.org/npm/latest'
$npmMeta | Select-Object version,engines
$npmMeta | ConvertTo-Json -Depth 15 | Set-Content work/tools/npm-metadata.json
Invoke-WebRequest $npmMeta.dist.tarball -OutFile work/tools/npm.tgz
$npmBytes = [System.IO.File]::ReadAllBytes((Join-Path (Get-Location) 'work/tools/npm.tgz'))
$npmIntegrity = 'sha512-' + [Convert]::ToBase64String([System.Security.Cryptography.SHA512]::HashData($npmBytes))
if ($npmIntegrity -ne $npmMeta.dist.integrity) { throw 'npm archive integrity mismatch' }
'Archive SHA-512 integrity verified'
tar -xzf work/tools/npm.tgz -C work/tools/npm
if ($LASTEXITCODE -ne 0) { throw 'npm extraction failed' }
node work/tools/npm/package/bin/npm-cli.js --version
```

Added npm.cmd and npx.cmd using apply_patch. Verification commands:

```powershell
.\npm.cmd --version
.\npx.cmd --version
node -e "const p=require('./work/tools/npm/package/package.json');const s=require('./work/tools/npm/package/node_modules/semver');console.log(JSON.stringify({npm:p.version,requiredNode:p.engines.node,actualNode:process.version,compatible:s.satisfies(process.version,p.engines.node)}))"
.\.venv\Scripts\python.exe -m pip check
git status --short --branch
```

Results: npm and npx 12.2.1; Node v24.22.1 satisfies npm's requirement `^22.22.2 || ^24.15.0 || >=26.0.0`; pip reports no broken requirements. Git has no commits. No contributor or AI co-author attribution added. No privileged installation, login, or browser authorization performed.

The report was appended with Add-Content and copied with `Copy-Item docs/SETUP_STATUS.md outputs/SETUP_STATUS.md`.

Single next action: provide Raah's source/manifests or describe the application to build. Project dependency installation remains blocked solely by the absence of project requirements; Python prerelease compatibility remains unverified.
