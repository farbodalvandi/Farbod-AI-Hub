# Farbod AI-Hub v6

Changes:
- New black/violet premium AI theme inspired by the requested Sellix/MotionSites visual direction (original implementation; no copied site assets).
- Higher contrast light mode on Hub and application shell.
- Global sidebar simplified: Asset Manager's detailed inventory menus are no longer repeated in other modules.
- Hardware Monitoring now has a direct device registry. HPE iLO targets can be added by IP + username + password and tested through Redfish.
- Monitoring credentials are encrypted locally using Fernet before database storage. TLS verification is optional for self-signed iLO environments.
- Equipment workspaces are pre-seeded with: Pasargad bank, Taavon bank, Dotin, Resalat bank, Refah bank, Karafarin bank, Gardeshgari bank, Riton.
- Existing user-created equipment banks and data are preserved.

Monitoring note: current live connector is HPE iLO Redfish. Dell iDRAC, storage and SAN connectors are shown as planned targets but are not falsely presented as implemented.
