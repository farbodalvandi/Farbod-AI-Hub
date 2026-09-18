# Version 10 notes

Version 10 adds unified asset and document search, assistant evidence links,
content indexing and the redesigned AI assistant interface.

This package is the macOS source edition. Create a virtual environment with
`./scripts/setup_macos.sh` and run it from VS Code or `./scripts/run_dev.sh`.

Existing `instance/`, `knowledge/` and upload folders may be copied into the
new project before startup. Keep a backup first; database migrations run when
the application imports.

Ollama is optional. Configure its URL and model with environment variables in
`.env.example`. Without Ollama, unified search and retrieved evidence remain
available, while generated answers are disabled.
