"""Application adapters; never expose stored filesystem paths to the browser."""
import os
import threading
import database as db
import paths
from document_search import DocumentIndex, search_assets

SOURCE_MODULES = {"Knowledge": "knowledge", "Equipment": "equipment_profile", "Bank connections": "equipment_profile", "Asset attachments": "asset_manager"}
_index = None
_lock = threading.RLock()
_worker = None
_error = None

def index():
    global _index
    with _lock:
        if _index is None:
            _index = DocumentIndex(os.path.join(paths.data_dir(), "instance", "document_index.sqlite3"))
        return _index

def catalog():
    documents = []
    def add(rows, source, folder, route):
        for row in rows:
            row = dict(row)
            description = " ".join(str(row.get(k) or "") for k in ("description", "category", "bank_name", "sub_name", "asset_name", "asset_context"))
            documents.append({"key": f"{source}:{row['id']}", "source": source, "name": row["original_name"],
                              "description": description, "path": os.path.join(paths.data_dir(), folder, row["stored_name"]),
                              "url": route.format(row["id"])})
    conn = db.get_conn()
    try:
        add(conn.execute("SELECT * FROM knowledge_files"), "Knowledge", "knowledge", "/knowledge/raw/{}")
        add(conn.execute("SELECT ef.*,es.name sub_name,eb.name bank_name FROM equipment_bank_files ef JOIN equipment_bank_subcategories es ON es.id=ef.subcategory_id JOIN equipment_banks eb ON eb.id=es.bank_id"), "Equipment", "equipment_files", "/equipment/file/{}")
        add(conn.execute("SELECT * FROM bank_connection_files"), "Bank connections", "bank_connection_info", "/equipment/bank-connection/file/{}")
        attachments = []
        for row in conn.execute("SELECT f.*,s.name asset_name,s.parent_table,s.parent_id FROM sub_object_files f JOIN sub_objects s ON s.id=f.sub_object_id"):
            row = dict(row)
            if row["parent_table"] in db.SCHEMAS:
                parent = conn.execute(f'SELECT * FROM "{row["parent_table"]}" WHERE id=?', (row["parent_id"],)).fetchone()
                if parent:
                    row["asset_context"] = " ".join(str(v or "") for v in dict(parent).values())
            attachments.append(row)
        add(attachments, "Asset attachments", "subobject_files", "/subobjects/file/{}")
    finally:
        conn.close()
    return documents

def synchronize(force=False):
    global _error
    # Acquire the service lock before taking a catalog snapshot to avoid stale writers.
    with _lock:
        try:
            index().sync(catalog(), force=force)
            _error = None
        except Exception:
            _error = "Document indexing failed. Check application logs and retry."
            raise

def start_sync(force=False):
    global _worker
    if _worker and _worker.is_alive():
        return False
    def work():
        try:
            synchronize(force)
        except Exception:
            import logging
            logging.exception("Document indexing failed")
    _worker = threading.Thread(target=work, daemon=True, name="FarbodDocumentIndex")
    _worker.start()
    return True

def status(sources):
    if _worker and _worker.is_alive():
        return {"busy": True, "documents": None, "ready": None, "issues": [], "error": None}
    return {**index().status(sources), "busy": False, "error": _error}

def files(query, sources):
    synchronize()
    return index().search(query, sources)

def assets(query):
    records = []
    for table, spec in db.SCHEMAS.items():
        for row in db.list_assets(table):
            fields = {label: row[key] for key, label, *_ in spec["fields"]}
            records.append({"table": table, "id": row["id"], "label": db.asset_label(table, row),
                            "fields": fields, "url": f"/assets/{table}/{row['id']}"})
    return search_assets(query, records)
