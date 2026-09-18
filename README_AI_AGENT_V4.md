# Farbod AI-Hub v4 — Agent Workspace

This build moves the application toward an AI-first infrastructure workspace.

## Added
- AI Orchestrator with Asset, Knowledge and Monitoring agents.
- Permission-aware read-only context collection.
- Agent Activity panel showing each analysis stage.
- Evidence cards for assets, indexed documents and monitoring state.
- Intent routing for search, diagnostics, firmware and document questions.
- Optional local Ollama provider with grounded context; local deterministic synthesis remains the default.
- New three-pane AI Assistant UI and motion/animation layer.
- Farbod AI-Hub branding throughout application text/configuration.

## Optional local LLM
Set environment variables before starting:

    FARBOD_AI_PROVIDER=ollama
    FARBOD_OLLAMA_URL=http://127.0.0.1:11434
    FARBOD_OLLAMA_MODEL=llama3.2

If Ollama is unavailable, Farbod AI-Hub automatically falls back to its local agent synthesis and search engine.

## Safety model
The current agent is intentionally read-only. Future infrastructure actions should use an approval workflow and audit log before execution.

## v7 Monitoring connectors
Live connector adapters are included for HPE iLO Redfish, Dell iDRAC Redfish, Dell EMC Unity REST, Dell PowerStore REST, and Brocade FOS REST. Endpoint support depends on the target firmware/API version and account permissions. The Monitoring Agent performs a fresh read-only probe and summarizes live identity/health/firmware context. No write/power/configuration action is performed.
