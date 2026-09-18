# Farbod AI-Hub — Intelligent Infrastructure Workspace

This build extends the existing application without replacing the current Asset Manager database or CRUD workflow.

## Added in this build
- New Intelligent AI-Hub landing page
- AI Assistant workspace (offline/local search mode)
- Global AI File Search
- Content search in XLSX, DOCX, PDF, CSV and TXT (PDF requires `pypdf`)
- Knowledge metadata/content search
- Equipment file search with Excel sheet + row and PDF page location
- Hardware Monitoring / NOC-style inventory status view
- New AI/Monitoring/File Search navigation
- Dark/Light compatible modern workspace styling and subtle animations
- Role-aware access to AI Assistant and Monitoring

## AI architecture note
The included AI Assistant is deliberately an offline-safe context/search layer. It does not transmit infrastructure data to any external LLM. It is ready to be extended with a configurable Local LLM or approved API provider later. Permission filtering should remain ahead of any future LLM context builder.

## Install / update dependencies
`pip install -r requirements.txt`

## Run
`python app.py`

Run the application directly from its Python source using the macOS scripts in `scripts/`.
