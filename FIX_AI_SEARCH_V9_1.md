# Farbod AI-Hub v9.1 – AI Asset Search Fix

Fixes:
- Corrected AI File Search table names to the actual SQLite schema:
  `equipment_bank_files` and `equipment_bank_subcategories`.
- Prevents a missing/failed file index from crashing the whole AI Assistant.
- Added natural-language asset search expansion. Queries such as
  `list all dl380 g10 servers`, `show DL380 Gen10`, and `find dl380` now
  search Asset Manager inventory using useful model tokens and G10/Gen10 aliases.
- Asset Manager remains the source of truth for inventory results.

For an existing EXE installation, rebuild the EXE from this package so the fixes
are included in the executable. Existing SQLite data in the application data
folder is not intended to be deleted.
