# Farbod AI-Hub v11 — Spatial macOS source edition

Farbod AI-Hub is a Flask-based infrastructure workspace for asset management,
knowledge files, equipment profiles, monitoring and AI-assisted search. This
edition runs directly from Python source and contains no EXE/PyInstaller build.

Version 11 introduces a spatial enterprise interface, live infrastructure
summary cards, an interactive AI core landing page, improved monitoring
context, and an Asset 360° profile for every inventory record. AI asset search
results now open the matching 360° profile directly.

## Requirements

- macOS with Python 3.11 or newer
- VS Code with the Microsoft Python extension
- Optional: Ollama for locally generated AI answers
- Optional: Tesseract (`brew install tesseract`) for OCR

## First setup

Open the extracted project folder in VS Code, then run:

```bash
chmod +x scripts/*.sh
./scripts/setup_macos.sh
./scripts/run_dev.sh
```

Open <http://127.0.0.1:5000>. The initial account is `admin` / `admin123`.
Change this password immediately after the first login.

VS Code automatically uses `.venv/bin/python`. You can also press **F5** and
select **Farbod AI-Hub: Development** to run and debug the application.

## Daily development workflow

```bash
source .venv/bin/activate
python app.py
```

Run tests before committing changes:

```bash
python -m pytest -q
```

## Production-style execution on macOS

The Flask development server is for coding and debugging. For stable LAN use:

```bash
./scripts/run_production.sh
```

The production script runs Gunicorn on `0.0.0.0:5000` by default. Override it
without modifying code:

```bash
FARBOD_ASSET_HOST=192.168.100.200 FARBOD_ASSET_PORT=5000 ./scripts/run_production.sh
```

For HTTPS/443, place Caddy or Nginx in front of Gunicorn and keep this app on a
non-privileged local port. Enable `FARBOD_ASSET_TRUST_PROXY=1` only behind a
trusted reverse proxy that sets forwarding headers.

## Environment variables

See `.env.example` for standard local settings.

| Variable | Default | Purpose |
|---|---:|---|
| `FARBOD_ASSET_HOST` | `127.0.0.1` dev / `0.0.0.0` production | Listen address |
| `FARBOD_ASSET_PORT` | `5000` | Listen port |
| `FARBOD_DATA_DIR` | project folder | Database and uploaded data location |
| `FARBOD_ASSET_TRUST_PROXY` | `0` | Trust proxy forwarding headers |
| `FLASK_DEBUG` | `0` | Development debugger/reloader |

## Project structure

```text
Farbod_AI-Hub/
├── app.py                  Flask routes and development entry point
├── wsgi.py                 Gunicorn production entry point
├── database.py             SQLite schema, migrations and queries
├── ai_engine.py            AI assistant integration
├── document_search.py      Knowledge indexing and retrieval
├── monitoring_connectors.py Infrastructure device connectors
├── paths.py                Resource and writable-data paths
├── requirements.txt        Runtime dependencies
├── requirements-test.txt   Development/test dependencies
├── scripts/                macOS setup and run commands
├── .vscode/                Debugger, interpreter and test settings
├── templates/              Jinja HTML templates
├── static/                 CSS, JavaScript, images and offline vendors
├── tests/                  Automated tests
└── instance/               Runtime database and keys (created locally)
```

The `instance/`, uploaded files, secrets and local virtual environment are
excluded from Git. Back up `instance/dcam.db`, the secret key and uploaded data
together when moving the application to another Mac or server.
