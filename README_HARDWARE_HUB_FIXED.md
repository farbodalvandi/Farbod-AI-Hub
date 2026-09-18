# Farbod AI-Hub

Source-based enterprise asset and infrastructure portal for macOS development.

## Access
- Initial login: `admin / admin123` (change it in **Setting** immediately).
- **Admin:** all four menus + user/role/password management.
- **Management:** Farbod Asset Manager with edit rights.
- **Operator:** view-only Farbod Asset Manager + Knowledge.

## Equipment Banks
Equipment provides a **Bank Name** sidebar. Create banks, add subcategories, then upload and open Excel, PDF and Word files.

## Theme
Light/Dark theme is available from the AI-Hub and module pages and is persisted in the browser.

## Update — Equipment files / Bank Connection Info / bulk delete
- Equipment subcategory uploads now require a **Description** and support common document/image/archive formats.
- Added **Bank Connection Info** section under Equipment with its own file library; Description is mandatory.
- Added file upload capability to asset **Components / Sub-objects**; every upload requires Description.
- Added multi-select + **Delete Selected** for **Servers** and **Storage** (Management/Admin only).
- Fixed the legacy `editor` permission mapping so Management can create/edit assets as intended.
- Fixed the malformed legacy `sub_objects` table definition that could cause a fresh database initialization failure.
