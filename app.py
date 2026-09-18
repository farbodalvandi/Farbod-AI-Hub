# -*- coding: utf-8 -*-
"""
Farbod AI-Hub - Enterprise Infrastructure Platform
Run:
    pip install flask openpyxl
    python3 app.py
Then open http://127.0.0.1:5000  (default login: admin / admin123 - change it in Setting!)
"""

import csv
import io
import os
import secrets
import uuid
import json
import urllib.request
import urllib.error
import ssl
import base64
import ipaddress
from datetime import datetime

from flask import (Flask, render_template, request, redirect, url_for,
                    session, flash, jsonify, send_file, abort)
from werkzeug.security import check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet

import database as db
from auth import login_required, role_required, current_user
import visio_export
import paths
from ai_engine import InfrastructureAgent
import search_service
from monitoring_connectors import probe as probe_monitoring, CONNECTORS as MONITORING_CONNECTORS

try:
    from openpyxl import Workbook
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

RESOURCE_DIR = paths.resource_dir()   # bundled templates/static (read-only)
BASE_DIR = paths.data_dir()           # writable application data
SECRET_FILE = os.path.join(BASE_DIR, "instance", "secret.key")

app = Flask(
    __name__,
    template_folder=os.path.join(RESOURCE_DIR, "templates"),
    static_folder=os.path.join(RESOURCE_DIR, "static"),
)
# ISO images are large; allow big uploads (default 16GB, override via env var).
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("FARBOD_ASSET_MAX_UPLOAD_MB", "16384")) * 1024 * 1024

# AI-Hub / Knowledge module
KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
KNOWLEDGE_CATEGORIES = {
    "server": "Server",
    "storage": "Storage",
    "sanswitch": "SAN Switch",
}
KNOWLEDGE_EXTENSIONS = {".pdf", ".doc", ".docx"}


def _load_secret():
    os.makedirs(os.path.dirname(SECRET_FILE), exist_ok=True)
    if os.path.exists(SECRET_FILE):
        return open(SECRET_FILE, "r").read().strip()
    key = secrets.token_hex(32)
    with open(SECRET_FILE, "w") as f:
        f.write(key)
    return key


app.secret_key = _load_secret()

def _credential_cipher():
    import hashlib, base64 as _b64
    return Fernet(_b64.urlsafe_b64encode(hashlib.sha256(app.secret_key.encode()).digest()))

def _encrypt_secret(value): return _credential_cipher().encrypt(value.encode()).decode()
def _decrypt_secret(value): return _credential_cipher().decrypt(value.encode()).decode()
# Honor forwarding headers only when explicitly running behind a trusted proxy.
if os.environ.get("FARBOD_ASSET_TRUST_PROXY", "0") not in ("0", "false", "False"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Initialize/migrate the database with a useful startup error.
try:
    db.init_db()
except Exception as exc:
    _startup_error_placeholder = None
    try:
        os.makedirs(BASE_DIR, exist_ok=True)
        with open(os.path.join(BASE_DIR, "startup.log"), "a", encoding="utf-8") as f:
            import traceback
            f.write("\n--- database initialization failure %s ---\n" % datetime.now().isoformat())
            traceback.print_exc(file=f)
    except Exception:
        pass
    raise


@app.errorhandler(500)
def internal_server_error(error):
    # Keep the browser response friendly while writing the full traceback for
    # diagnosis.
    try:
        import traceback
        log_path = os.path.join(paths.data_dir(), "server_error.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n--- HTTP 500 %s ---\n" % datetime.now().isoformat())
            traceback.print_exc(file=f)
    except Exception:
        log_path = "server_error.log"
    return render_template("error.html", log_path=log_path), 500


@app.template_filter("todict")
def todict_filter(row):
    return dict(row) if row is not None else {}


@app.context_processor
def inject_globals():
    return {"SCHEMAS": db.SCHEMAS, "current_user": current_user(), "ROLE_LEVEL": db.ROLE_LEVEL,
            "db_sub_files": db.list_sub_object_files, "APP_VERSION": "11.0"}


@app.before_request
def update_live_presence():
    username = session.get("username")
    if username:
        sid = session.get("presence_id")
        if not sid:
            sid = secrets.token_urlsafe(16)
            session["presence_id"] = sid
        db.touch_presence(username, sid, request.remote_addr)


@app.route("/api/online-users")
@login_required
def online_users_api():
    users = db.online_users()
    return jsonify({"count": len(users), "users": [dict(u) for u in users]})


@app.route("/healthz")
def healthz():
    """Small endpoint for service and reverse-proxy health checks."""
    return jsonify({"status": "ok", "service": "FarbodAIHub"})

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.get_user(username)
        if user and user["active"] and check_password_hash(user["password_hash"], password):
            session["username"] = username
            session["presence_id"] = secrets.token_urlsafe(16)
            db.touch_presence(username, session["presence_id"], request.remote_addr)
            db.log_action(username, "login", "")
            return redirect(request.args.get("next") or url_for("hardware_hub"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    if session.get("username"):
        db.remove_presence(session["username"], session.get("presence_id"))
        db.log_action(session["username"], "logout", "")
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# AI-Hub / independent module authentication
# ---------------------------------------------------------------------------

MODULES = {
    "asset_manager": {"title": "Farbod Asset Manager", "icon": "bi-hdd-stack-fill",
                      "description": "Inventory, assets, SAN, storage and data-center management."},
    "knowledge": {"title": "Knowledge", "icon": "bi-book-half",
                  "description": "Technical knowledge base and technical documents."},
    "equipment_profile": {"title": "Equipment", "icon": "bi-cpu-fill",
                          "description": "Equipment banks, subcategories and technical documents."},
    "ai_assistant": {"title": "AI Assistant", "icon": "bi-stars",
                     "description": "Context-aware infrastructure search and analysis workspace."},
    "monitoring": {"title": "Hardware Monitoring", "icon": "bi-activity",
                   "description": "NOC-style inventory health, status and alert workspace."},
    "settings": {"title": "Setting", "icon": "bi-sliders2",
                 "description": "Users, roles, passwords and system settings."},
}
ROLE_MODULES = {
    "admin": set(MODULES),
    "manager": {"asset_manager", "knowledge", "equipment_profile", "ai_assistant", "monitoring"},
    "operator": {"asset_manager", "knowledge", "ai_assistant", "monitoring"},
}

def module_allowed(module_key):
    user=current_user()
    return bool(user and module_key in ROLE_MODULES.get(user["role"], set()))

def module_required(module_key):
    def decorator(view):
        from functools import wraps
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user():
                return redirect(url_for("login", next=request.path))
            key=kwargs.get("module_key") if module_key=="__dynamic__" else module_key
            if key not in MODULES or not module_allowed(key):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator

@app.route("/hardware-hub")
@login_required
def hardware_hub():
    summary, _ = _status_summary()
    devices = db.list_monitoring_devices()
    connected = sum(1 for d in devices if str(d["status"] or "").lower() in
                    {"ok", "online", "healthy", "enabled"})
    coverage = search_service.status(_search_sources()) if _search_sources() else {}
    knowledge_count = coverage.get("documents") or 0
    return render_template("hardware_hub.html", modules=MODULES,
                           allowed_modules=ROLE_MODULES.get(current_user()["role"], set()),
                           summary=summary, monitored=len(devices), connected=connected,
                           knowledge_count=knowledge_count)

@app.route("/module-login/<module_key>", methods=["GET", "POST"])
@login_required
def module_login(module_key):
    if module_key not in MODULES or not module_allowed(module_key): abort(403)
    target = (url_for("knowledge_home") if module_key=="knowledge" else
              url_for("dashboard") if module_key=="asset_manager" else
              url_for("equipment_profile") if module_key=="equipment_profile" else
              url_for("ai_assistant") if module_key=="ai_assistant" else
              url_for("monitoring") if module_key=="monitoring" else url_for("settings"))
    return redirect(target)

@app.route("/module-logout/<module_key>")
@login_required
def module_logout(module_key):
    return redirect(url_for("hardware_hub"))

@app.route("/equipment")
@module_required("equipment_profile")
def equipment_profile():
    banks=db.list_equipment_banks()
    selected_id=request.args.get("bank", type=int)
    selected_bank=db.get_equipment_bank(selected_id) if selected_id else (banks[0] if banks else None)
    subs=db.list_equipment_subcategories(selected_bank["id"]) if selected_bank else []
    selected_sub_id=request.args.get("sub", type=int)
    selected_sub=db.get_equipment_subcategory(selected_sub_id) if selected_sub_id else (subs[0] if subs else None)
    files=db.list_equipment_files(selected_sub["id"]) if selected_sub else []
    return render_template("equipment.html", banks=banks, selected_bank=selected_bank, subs=subs, selected_sub=selected_sub, files=files)

@app.route("/equipment/bank", methods=["POST"])
@module_required("equipment_profile")
def equipment_bank_create():
    name=request.form.get("name","").strip()
    if not name: flash("Bank Name is required.","danger")
    else:
        try: db.create_equipment_bank(name); flash("Bank added successfully.","success")
        except Exception: flash("Bank already exists.","warning")
    return redirect(url_for("equipment_profile"))

@app.route("/equipment/bank/<int:bank_id>/delete", methods=["POST"])
@module_required("equipment_profile")
def equipment_bank_delete(bank_id):
    bank=db.get_equipment_bank(bank_id)
    if not bank:
        abort(404)
    stored_files=db.delete_equipment_bank(bank_id)
    for stored in stored_files:
        try:
            os.remove(os.path.join(EQUIPMENT_FILE_DIR, stored))
        except OSError:
            pass
    db.log_action(current_user()["username"], "equipment_bank_delete", bank["name"])
    flash(f'Bank "{bank["name"]}" and its subcategories/files were deleted.', "success")
    return redirect(url_for("equipment_profile"))

@app.route("/equipment/subcategory", methods=["POST"])
@module_required("equipment_profile")
def equipment_subcategory_create():
    bank_id=request.form.get("bank_id",type=int); name=request.form.get("name","").strip()
    if bank_id and name:
        try: db.create_equipment_subcategory(bank_id,name); flash("Subcategory added.","success")
        except Exception: flash("Subcategory already exists.","warning")
    return redirect(url_for("equipment_profile",bank=bank_id))

EQUIPMENT_FILE_EXTENSIONS={".xlsx":"Excel", ".xls":"Excel", ".pdf":"PDF", ".docx":"Word", ".doc":"Word", ".csv":"CSV", ".txt":"Text", ".png":"Image", ".jpg":"Image", ".jpeg":"Image", ".zip":"Archive"}
EQUIPMENT_FILE_DIR=os.path.join(paths.data_dir(),"equipment_files")
os.makedirs(EQUIPMENT_FILE_DIR,exist_ok=True)

@app.route("/equipment/file", methods=["POST"])
@module_required("equipment_profile")
def equipment_file_upload():
    sub_id=request.form.get("subcategory_id",type=int); f=request.files.get("file")
    sub=db.get_equipment_subcategory(sub_id) if sub_id else None
    if not sub or not f or not f.filename:
        flash("Select a subcategory and file.","danger")
        return redirect(url_for("equipment_profile"))
    ext=os.path.splitext(f.filename)[1].lower()
    if ext not in EQUIPMENT_FILE_EXTENSIONS:
        flash("Only Excel, PDF and Word files are accepted.","danger")
        return redirect(url_for("equipment_profile",sub=sub_id))
    original=f.filename; safe=secure_filename(original) or "document"+ext
    stored=uuid.uuid4().hex+"_"+safe; path=os.path.join(EQUIPMENT_FILE_DIR,stored); f.save(path)
    description=request.form.get("description", "").strip()
    if not description:
        try: os.remove(path)
        except OSError: pass
        flash("Description is required for every upload.","danger")
        return redirect(url_for("equipment_profile",bank=sub["bank_id"],sub=sub_id))
    db.add_equipment_file(sub_id,original,stored,EQUIPMENT_FILE_EXTENSIONS[ext],os.path.getsize(path),current_user()["username"],description)
    db.log_action(current_user()["username"],"equipment_file_upload",original)
    flash("File uploaded successfully.","success")
    return redirect(url_for("equipment_profile",bank=sub["bank_id"],sub=sub_id))

@app.route("/equipment/file/<int:file_id>")
@module_required("equipment_profile")
def equipment_file_view(file_id):
    row=db.get_equipment_file(file_id)
    if not row: abort(404)
    path=os.path.join(EQUIPMENT_FILE_DIR,row["stored_name"])
    if not os.path.exists(path): abort(404)
    return send_file(path,as_attachment=False,download_name=row["original_name"])

BANK_CONNECTION_DIR=os.path.join(paths.data_dir(),"bank_connection_info")
os.makedirs(BANK_CONNECTION_DIR,exist_ok=True)

@app.route("/equipment/bank-connection", methods=["GET", "POST"])
@module_required("equipment_profile")
def bank_connection_info():
    if request.method == "POST":
        f=request.files.get("file"); description=request.form.get("description","").strip()
        if not f or not f.filename: flash("Please choose a file to upload.","danger")
        elif not description: flash("Description is required for every upload.","danger")
        else:
            ext=os.path.splitext(f.filename)[1].lower()
            if ext not in EQUIPMENT_FILE_EXTENSIONS: flash("Unsupported file type.","danger")
            else:
                original=f.filename; safe=secure_filename(original) or ("document"+ext)
                stored=uuid.uuid4().hex+"_"+safe; path=os.path.join(BANK_CONNECTION_DIR,stored); f.save(path)
                db.add_bank_connection_file(original,stored,EQUIPMENT_FILE_EXTENSIONS[ext],os.path.getsize(path),current_user()["username"],description)
                db.log_action(current_user()["username"],"bank_connection_file_upload",original); flash("Bank Connection Info file uploaded successfully.","success")
        return redirect(url_for("bank_connection_info"))
    return render_template("bank_connection.html",files=db.list_bank_connection_files())

@app.route("/equipment/bank-connection/file/<int:file_id>")
@module_required("equipment_profile")
def bank_connection_file_view(file_id):
    row=db.get_bank_connection_file(file_id)
    if not row: abort(404)
    path=os.path.join(BANK_CONNECTION_DIR,row["stored_name"])
    if not os.path.exists(path): abort(404)
    return send_file(path,as_attachment=False,download_name=row["original_name"])

@app.route("/settings")
@module_required("settings")
def settings():
    return render_template("settings.html",users=db.list_users(),roles=db.ROLES)

@app.route("/module-users/<module_key>", methods=["GET", "POST"])
@role_required("admin")
def module_users(module_key):
    if module_key not in MODULES: abort(404)
    if request.method == "POST":
        action=request.form.get("action"); username=request.form.get("username","").strip(); password=request.form.get("password","")
        try:
            if action=="create":
                if len(username)<2 or len(password)<6: raise ValueError("Username must be 2+ and password 6+ characters.")
                db.create_module_user(module_key,username,password)
            elif action=="update":
                db.update_module_user(int(request.form["user_id"]),module_key,username,password or None,1 if request.form.get("active") else 0)
            elif action=="delete":
                if len(db.list_module_users(module_key))<=1: raise ValueError("At least one user must remain.")
                db.delete_module_user(int(request.form["user_id"]),module_key)
            flash("User operation completed successfully.","success")
        except Exception as e: flash(str(e),"danger")
        return redirect(url_for("module_users",module_key=module_key))
    return render_template("module_users.html",module=MODULES[module_key],module_key=module_key,users=db.list_module_users(module_key),current=session.get("module_auth_users",{}).get(module_key,""))

@app.route("/module-users/<module_key>/change-password", methods=["POST"])
@role_required("admin")
def module_change_password(module_key):
    current=session.get("module_auth_users",{}).get(module_key); user=db.get_module_user(module_key,current) if current else None; pw=request.form.get("new_password","")
    if not user or len(pw)<6 or pw!=request.form.get("confirm_password",""): flash("Password must match and contain at least 6 characters.","danger")
    else: db.update_module_user(user["id"],module_key,user["username"],pw,user["active"]); flash("Password changed successfully.","success")
    return redirect(url_for("module_users",module_key=module_key))

@app.route("/knowledge")
@module_required("knowledge")
def knowledge_home():
    return render_template("knowledge.html",
                           categories=KNOWLEDGE_CATEGORIES,
                           active_category=request.args.get("category", "server"),
                           files=db.list_knowledge_files(request.args.get("category", "server"))
                           if request.args.get("category", "server") in KNOWLEDGE_CATEGORIES else [])


@app.route("/knowledge/upload", methods=["POST"])
@module_required("knowledge")
def knowledge_upload():
    category = request.form.get("category", "")
    description = request.form.get("description", "").strip()
    uploaded = request.files.get("file")
    if category not in KNOWLEDGE_CATEGORIES:
        flash("Invalid Knowledge category.", "danger")
        return redirect(url_for("knowledge_home"))
    if not uploaded or not uploaded.filename:
        flash("Please select a PDF or Word file.", "warning")
        return redirect(url_for("knowledge_home", category=category))
    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in KNOWLEDGE_EXTENSIONS:
        flash("Only PDF, DOC and DOCX files are allowed.", "danger")
        return redirect(url_for("knowledge_home", category=category))
    if not description:
        flash("Description is required.", "warning")
        return redirect(url_for("knowledge_home", category=category))
    stored = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(KNOWLEDGE_DIR, stored)
    uploaded.save(dest)
    size = os.path.getsize(dest)
    media = "application/pdf" if ext == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ext == ".docx" else "application/msword"
    db.add_knowledge_file(category, secure_filename(uploaded.filename) or uploaded.filename,
                          stored, description, size, media, session.get("module_auth_users", {}).get("knowledge", "knowledge"))
    flash("Knowledge file uploaded successfully.", "success")
    return redirect(url_for("knowledge_home", category=category))


@app.route("/knowledge/file/<int:file_id>")
@module_required("knowledge")
def knowledge_file(file_id):
    row = db.get_knowledge_file(file_id)
    if not row:
        abort(404)
    path = os.path.join(KNOWLEDGE_DIR, row["stored_name"])
    if not os.path.isfile(path):
        abort(404)
    return render_template("knowledge_viewer.html", file=row)


@app.route("/knowledge/raw/<int:file_id>")
@module_required("knowledge")
def knowledge_raw(file_id):
    row = db.get_knowledge_file(file_id)
    if not row:
        abort(404)
    path = os.path.join(KNOWLEDGE_DIR, row["stored_name"])
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, mimetype=row["media_type"], as_attachment=False,
                     download_name=row["original_name"])


@app.route("/knowledge/docx/<int:file_id>")
@module_required("knowledge")
def knowledge_docx(file_id):
    row = db.get_knowledge_file(file_id)
    if not row or not row["original_name"].lower().endswith(".docx"):
        abort(404)
    path = os.path.join(KNOWLEDGE_DIR, row["stored_name"])
    try:
        from docx import Document
        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    except Exception as exc:
        flash(f"Could not render Word document: {exc}", "danger")
        return redirect(url_for("knowledge_file", file_id=file_id))
    return render_template("docx_viewer.html", file=row, paragraphs=paragraphs)


@app.route("/")
def root():
    return redirect(url_for("hardware_hub"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def _human_size(num_bytes):
    try:
        num_bytes = float(num_bytes or 0)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024 or unit == "TB":
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{int(num_bytes)} {unit}"
        num_bytes /= 1024


app.jinja_env.filters["filesize"] = _human_size



def _status_summary():
    summary={"total":0,"healthy":0,"warning":0,"critical":0,"unknown":0}
    items=[]
    for table,spec in db.SCHEMAS.items():
        for row in db.list_assets(table):
            d=dict(row); summary["total"]+=1
            raw=str(d.get("status") or "").lower()
            if any(x in raw for x in ("fault","critical","down","failed")): bucket="critical"
            elif any(x in raw for x in ("warn","maintenance","standby")): bucket="warning"
            elif any(x in raw for x in ("active","healthy","online","operational")): bucket="healthy"
            else: bucket="unknown"
            summary[bucket]+=1
            items.append({"table":table,"type":spec["label"],"id":d.get("id"),"name":db.asset_label(table,row),"status":d.get("status") or "Unknown","ip":d.get("management_ip") or d.get("ilo_ip") or "-","bucket":bucket})
    return summary,items

def _probe_monitoring(device):
    return probe_monitoring(device, _decrypt_secret(device["password_enc"]))

def _monitoring_agent_report(device, result):
    status=str(result.get("status") or "Unknown")
    low=status.lower()
    severity="Critical" if any(x in low for x in ("critical","failed","fault","down")) else ("Warning" if any(x in low for x in ("warning","degraded","minor")) else "Healthy")
    findings=[]
    if result.get("firmware"): findings.append(f"Reported firmware/BIOS: {result['firmware']}")
    if result.get("model"): findings.append(f"Detected model: {result['model']}")
    if result.get("serial_number"): findings.append(f"Serial/service identifier: {result['serial_number']}")
    findings.append(f"Live endpoint state: {status}")
    action=("Immediate administrator review is recommended; inspect hardware event logs and component health." if severity=="Critical" else "Review warnings and firmware baselines before maintenance." if severity=="Warning" else "No live health fault was reported by this endpoint. Continue normal monitoring.")
    return {"severity":severity,"findings":findings,"action":action,"details":result.get("details") or {}}

@app.route("/monitoring", methods=["GET","POST"])
@module_required("monitoring")
def monitoring():
    if request.method=="POST":
        name=request.form.get("name","").strip(); ip=request.form.get("management_ip","").strip(); user=request.form.get("username","").strip(); password=request.form.get("password","")
        try:
            ipaddress.ip_address(ip)
            if not all((name,ip,user,password)): raise ValueError("All fields are required.")
            did=db.create_monitoring_device(name,request.form.get("device_type","HPE iLO (Redfish)"),ip,user,_encrypt_secret(password),bool(request.form.get("verify_ssl")),current_user()["username"])
            flash("Monitoring target added. Use Test / Refresh for a live connector query.","success")
        except Exception as exc: flash("Could not add device: "+str(exc),"danger")
        return redirect(url_for("monitoring"))
    summary,items=_status_summary(); devices=db.list_monitoring_devices()
    return render_template("monitoring.html",summary=summary,items=items[:250],devices=devices,connector_names=list(MONITORING_CONNECTORS.keys()))

@app.route("/monitoring/<int:device_id>/probe",methods=["POST"])
@module_required("monitoring")
def monitoring_probe(device_id):
    d=db.get_monitoring_device(device_id)
    if not d: abort(404)
    try:
        result=_probe_monitoring(d); persist={k:v for k,v in result.items() if k != "details"}; db.update_monitoring_device_status(device_id,**persist); flash(f'{d["name"]}: live connection successful.',"success")
    except Exception as exc:
        db.update_monitoring_device_status(device_id,status="Connection Error",last_error=str(exc)[:500],last_seen=datetime.now().isoformat()); flash(f'{d["name"]}: connection failed — {exc}',"warning")
    return redirect(url_for("monitoring"))

@app.route("/monitoring/<int:device_id>/agent",methods=["POST"])
@module_required("monitoring")
def monitoring_agent(device_id):
    d=db.get_monitoring_device(device_id)
    if not d: abort(404)
    try:
        result=_probe_monitoring(d)
        persist={k:v for k,v in result.items() if k != "details"}
        db.update_monitoring_device_status(device_id,**persist)
        report=_monitoring_agent_report(d,result)
        return render_template("monitoring_agent.html",device=d,result=result,report=report)
    except Exception as exc:
        db.update_monitoring_device_status(device_id,status="Connection Error",last_error=str(exc)[:500],last_seen=datetime.now().isoformat())
        return render_template("monitoring_agent.html",device=d,result=None,report=None,error=str(exc)), 502

@app.route("/monitoring/<int:device_id>/delete",methods=["POST"])
@module_required("monitoring")
def monitoring_delete(device_id):
    db.delete_monitoring_device(device_id); flash("Monitoring target removed.","success"); return redirect(url_for("monitoring"))

def _search_sources():
    return [source for source, module in search_service.SOURCE_MODULES.items() if module_allowed(module)]

def _file_search(q):
    return search_service.files(q, _search_sources())

def _assistant_result(q):
    result = InfrastructureAgent(search_service.assets if module_allowed("asset_manager") else lambda q: [], _file_search).run(q)
    result["coverage"] = search_service.status(_search_sources())
    return result

@app.after_request
def _refresh_document_index(response):
    if request.method == "POST" and response.status_code < 400 and request.endpoint in {
        "knowledge_upload", "equipment_file_upload", "bank_connection_info", "sub_object_file_upload",
        "equipment_bank_delete", "sub_object_delete"}:
        search_service.start_sync()
    return response

@app.route("/ai-assistant", methods=["GET","POST"])
@module_required("ai_assistant")
def ai_assistant():
    q=(request.values.get("q") or "").strip()[:2000]
    session.setdefault("search_csrf", secrets.token_hex(32))
    search_service.start_sync()
    return render_template("ai_assistant.html", q=q, sources=_search_sources(),
                           ollama=os.getenv("FARBOD_AI_PROVIDER", "local").lower() == "ollama")

@app.route("/ai-assistant/query", methods=["POST"])
@module_required("ai_assistant")
def assistant_query():
    if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("search_csrf", "missing")):
        abort(403)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error="Send a JSON object containing q."), 400
    q = payload.get("q", "")
    if not isinstance(q, str) or not q.strip() or len(q) > 2000:
        return jsonify(error="Enter a question between 1 and 2,000 characters."), 400
    try:
        return jsonify(_assistant_result(q.strip()))
    except Exception:
        app.logger.exception("Assistant search failed")
        return jsonify(error="Search could not finish. Check document coverage and retry."), 500

@app.route("/ai-assistant/index-status")
@module_required("ai_assistant")
def assistant_index_status():
    return jsonify(search_service.status(_search_sources()))

@app.route("/ai-assistant/reindex", methods=["POST"])
@module_required("ai_assistant")
def assistant_reindex():
    if current_user()["role"] != "admin": abort(403)
    if not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), session.get("search_csrf", "missing")):
        abort(403)
    return jsonify(started=search_service.start_sync(force=True))

@app.route("/file-search")
@login_required
def file_search():
    return redirect(url_for("ai_assistant", q=request.args.get("q", "").strip()[:2000]))

@app.route("/dashboard")
@login_required
def dashboard():
    counts = {}
    for table in db.SCHEMAS:
        counts[table] = len(db.list_assets(table))
    isos = db.list_iso_files()
    summary, _ = _status_summary()
    devices = db.list_monitoring_devices()
    recent_activity = db.list_system_logs(6)
    return render_template("dashboard.html", counts=counts, isos=isos,
                           summary=summary, monitoring_devices=devices,
                           recent_activity=recent_activity)


@app.route("/search")
@login_required
def global_search():
    q = request.args.get("q", "").strip()
    if module_allowed("ai_assistant"):
        return redirect(url_for("ai_assistant", q=q))
    results = db.search_all_assets(q) if q else []
    iso_results = []
    if q:
        like = f"%{q}%"
        conn = db.get_conn()
        iso_results = conn.execute(
            "SELECT * FROM iso_files WHERE original_name LIKE ? OR notes LIKE ? ORDER BY id DESC LIMIT 50",
            (like, like)).fetchall()
        conn.close()
    return render_template("search.html", q=q, results=results, iso_results=iso_results)


# ---------------------------------------------------------------------------
# ISO file library (shown as an "ISO File" card on the dashboard)
# ---------------------------------------------------------------------------

@app.route("/isos/upload", methods=["POST"])
@role_required("editor")
def iso_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Please choose a file to upload.", "danger")
        return redirect(url_for("dashboard"))

    original_name = file.filename
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in (".iso", ".vsdx"):
        flash("Only .iso and .vsdx files are accepted.", "danger")
        return redirect(url_for("dashboard"))

    media_type = "vsdx" if ext == ".vsdx" else "iso"
    safe_base = secure_filename(original_name) or ("diagram.vsdx" if media_type == "vsdx" else "image.iso")
    stored_name = f"{uuid.uuid4().hex}_{safe_base}"
    dest_path = os.path.join(paths.iso_dir(), stored_name)

    file.save(dest_path)  # streamed to disk, safe for multi-GB files
    size_bytes = os.path.getsize(dest_path)

    db.add_iso_file(original_name, stored_name, size_bytes,
                     request.form.get("notes", "").strip(),
                     current_user()["username"], media_type=media_type)
    db.log_action(current_user()["username"], "media_upload", f"{media_type}:{original_name}")
    flash(f'"{original_name}" uploaded successfully.', "success")
    return redirect(url_for("dashboard"))


@app.route("/isos/<int:iso_id>/view")
@login_required
def iso_view(iso_id):
    row = db.get_iso_file(iso_id)
    if not row or (row["media_type"] or "").lower() != "vsdx":
        abort(404)
    file_path = os.path.join(paths.iso_dir(), row["stored_name"])
    if not os.path.exists(file_path):
        abort(404)
    try:
        page_index = max(0, int(request.args.get("page", "0")))
    except ValueError:
        page_index = 0
    try:
        with open(file_path, "rb") as f:
            svg, page_count, page_index = visio_export.import_vsdx_svg(
                f.read(), page_index=page_index)
    except Exception as exc:
        try:
            with open(os.path.join(paths.data_dir(), "server_error.log"), "a", encoding="utf-8") as log:
                import traceback
                log.write("\\n--- VSDX viewer failure %s ---\\n" % datetime.now().isoformat())
                traceback.print_exc(file=log)
        except Exception:
            pass
        return render_template("error.html",
                               log_path=os.path.join(paths.data_dir(), "server_error.log")), 500
    return render_template("vsdx_viewer.html", row=row, svg=svg,
                           page_count=page_count, page_index=page_index)

@app.route("/isos/<int:iso_id>/download")
@login_required
def iso_download(iso_id):
    row = db.get_iso_file(iso_id)
    if not row:
        abort(404)
    file_path = os.path.join(paths.iso_dir(), row["stored_name"])
    if not os.path.exists(file_path):
        flash("This ISO file is missing from disk.", "danger")
        return redirect(url_for("dashboard"))
    return send_file(file_path, as_attachment=True, download_name=row["original_name"])


@app.route("/isos/<int:iso_id>/delete", methods=["POST"])
@role_required("manager")
def iso_delete(iso_id):
    row = db.get_iso_file(iso_id)
    if row:
        file_path = os.path.join(paths.iso_dir(), row["stored_name"])
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass
        db.delete_iso_file(iso_id)
        db.log_action(current_user()["username"], "media_delete", f"{row['media_type']}:{row['original_name']}")
        flash(f'"{row["original_name"]}" deleted.', "warning")
    return redirect(url_for("dashboard"))


# ---------------------------------------------------------------------------
# Generic asset CRUD (flexible modal-based add/edit windows in the template)
# ---------------------------------------------------------------------------

@app.route("/assets/<table>")
@login_required
def asset_list(table):
    if table not in db.SCHEMAS:
        abort(404)
    q = request.args.get("q", "").strip()
    rows = db.list_assets(table, q or None)
    return render_template("list.html", table=table, spec=db.SCHEMAS[table],
                            rows=rows, q=q,
                            lookups={f[3]: db.get_lookup(f[3]) for f in db.SCHEMAS[table]["fields"] if f[3]})


def _asset_health(row):
    raw = str(row["status"] if "status" in row.keys() else "").lower()
    if any(x in raw for x in ("fault", "critical", "down", "failed", "offline")):
        return "critical"
    if any(x in raw for x in ("warn", "maintenance", "standby", "degraded")):
        return "warning"
    if any(x in raw for x in ("active", "healthy", "online", "operational", "ok")):
        return "healthy"
    return "unknown"


@app.route("/assets/<table>/<int:row_id>")
@login_required
def asset_detail(table, row_id):
    if table not in db.SCHEMAS:
        abort(404)
    asset = db.get_asset(table, row_id)
    if not asset:
        abort(404)
    spec = db.SCHEMAS[table]
    fields = [{"key": key, "label": label, "value": asset[key] or ""}
              for key, label, _field_type, _lookup in spec["fields"]]
    populated = [field for field in fields if str(field["value"]).strip()]
    relationships = []
    for link in db.links_for(table, row_id):
        is_source = link["source_table"] == table and link["source_id"] == row_id
        other_table = link["target_table"] if is_source else link["source_table"]
        other_id = link["target_id"] if is_source else link["source_id"]
        other = db.get_asset(other_table, other_id) if other_table in db.SCHEMAS else None
        relationships.append({"link": link, "table": other_table, "id": other_id,
                              "label": db.asset_label(other_table, other) if other is not None else f"{other_table} #{other_id}",
                              "type": db.SCHEMAS.get(other_table, {}).get("label", other_table),
                              "direction": "outbound" if is_source else "inbound"})
    components = db.list_sub_objects(table, row_id)
    identity_values = [asset[k] for k in ("serial_number", "management_ip", "ilo_ip")
                       if k in asset.keys() and asset[k]]
    monitoring_device = None
    for device in db.list_monitoring_devices():
        if device["management_ip"] in identity_values or (device["serial_number"] and device["serial_number"] in identity_values):
            monitoring_device = device
            break
    marker = f"{table}#{row_id}"
    activity = [row for row in db.list_system_logs(200) if marker in str(row["details"] or "")][:8]
    return render_template("asset_detail.html", table=table, row_id=row_id, asset=asset,
                           spec=spec, fields=fields, populated=populated,
                           completion=round((len(populated) / max(1, len(fields))) * 100),
                           health=_asset_health(asset), relationships=relationships,
                           components=components, monitoring_device=monitoring_device,
                           activity=activity)


@app.route("/assets/<table>/new", methods=["POST"])
@role_required("editor")
def asset_create(table):
    if table not in db.SCHEMAS:
        abort(404)
    db.create_asset(table, request.form, current_user()["username"])
    flash("New record created successfully.", "success")
    return redirect(url_for("asset_list", table=table))


@app.route("/assets/<table>/<int:row_id>/edit", methods=["POST"])
@role_required("editor")
def asset_edit(table, row_id):
    if table not in db.SCHEMAS:
        abort(404)
    db.update_asset(table, row_id, request.form, current_user()["username"])
    flash("Record updated successfully.", "success")
    return redirect(url_for("asset_list", table=table))


@app.route("/assets/<table>/<int:row_id>/delete", methods=["POST"])
@role_required("manager")
def asset_delete(table, row_id):
    if table not in db.SCHEMAS:
        abort(404)
    db.delete_asset(table, row_id, current_user()["username"])
    flash("Record deleted successfully.", "warning")
    return redirect(url_for("asset_list", table=table))

@app.route("/assets/<table>/bulk-delete", methods=["POST"])
@role_required("manager")
def asset_bulk_delete(table):
    if table not in ("servers", "storage"): abort(403)
    ids=[]
    for raw in request.form.getlist("selected_ids"):
        try:
            v=int(raw)
            if v>0: ids.append(v)
        except (TypeError,ValueError): pass
    ids=list(dict.fromkeys(ids))
    if not ids: flash("No equipment selected.","warning")
    else: flash(f"{db.delete_assets(table,ids,current_user()["username"])} selected equipment record(s) deleted.","warning")
    return redirect(url_for("asset_list", table=table))


@app.route("/assets/<table>/<int:row_id>/subobjects", methods=["GET", "POST"])
@login_required
def sub_objects(table, row_id):
    if table not in db.SCHEMAS:
        abort(404)
    if request.method == "POST":
        if db.ROLE_LEVEL[current_user()["role"]] < db.ROLE_LEVEL["editor"]:
            abort(403)
        db.add_sub_object(table, row_id, request.form.get("name", ""),
                           request.form.get("obj_type", ""), request.form.get("notes", ""))
        db.log_action(current_user()["username"], "subobject_create", f"{table}#{row_id}:{request.form.get('name','')}")
        return redirect(url_for("sub_objects", table=table, row_id=row_id))
    asset = db.get_asset(table, row_id)
    if not asset:
        abort(404)
    subs = db.list_sub_objects(table, row_id)
    return render_template("subobjects.html", table=table, spec=db.SCHEMAS[table],
                            asset=asset, subs=subs)


SUBOBJECT_FILE_DIR=os.path.join(paths.data_dir(),"subobject_files")
os.makedirs(SUBOBJECT_FILE_DIR,exist_ok=True)

@app.route("/subobjects/<int:sub_id>/file", methods=["POST"])
@role_required("editor")
def sub_object_file_upload(sub_id):
    sub=db.get_sub_object(sub_id)
    if not sub: abort(404)
    f=request.files.get("file"); description=request.form.get("description","").strip()
    if not f or not f.filename or not description:
        flash("File and Description are required.","danger")
        return redirect(request.referrer or url_for("dashboard"))
    ext=os.path.splitext(f.filename)[1].lower()
    if ext not in EQUIPMENT_FILE_EXTENSIONS:
        flash("Unsupported file type.","danger")
        return redirect(request.referrer or url_for("dashboard"))
    original=f.filename; safe=secure_filename(original) or ("document"+ext)
    stored=uuid.uuid4().hex+"_"+safe; path=os.path.join(SUBOBJECT_FILE_DIR,stored); f.save(path)
    db.add_sub_object_file(sub_id,original,stored,EQUIPMENT_FILE_EXTENSIONS[ext],os.path.getsize(path),current_user()["username"],description)
    db.log_action(current_user()["username"],"subobject_file_upload",f"subobject#{sub_id}:{original}")
    flash("File uploaded successfully.","success")
    return redirect(request.referrer or url_for("dashboard"))

@app.route("/subobjects/file/<int:file_id>")
@login_required
def sub_object_file_view(file_id):
    row=db.get_sub_object_file(file_id)
    if not row: abort(404)
    path=os.path.join(SUBOBJECT_FILE_DIR,row["stored_name"])
    if not os.path.exists(path): abort(404)
    return send_file(path,as_attachment=False,download_name=row["original_name"])

@app.route("/subobjects/<int:sub_id>/delete", methods=["POST"])
@role_required("manager")
def sub_object_delete(sub_id):
    db.delete_sub_object(sub_id)
    db.log_action(current_user()["username"], "subobject_delete", f"subobject#{sub_id}")
    return redirect(request.referrer or url_for("dashboard"))


# ---------------------------------------------------------------------------
# Lookup (dropdown) management - add / rename / delete values live
# ---------------------------------------------------------------------------

@app.route("/lookups")
@role_required("manager")
def lookups_page():
    keys = db.all_lookup_keys()
    data = {}
    conn = db.get_conn()
    for k in keys:
        data[k] = conn.execute(
            "SELECT * FROM lookups WHERE field_key=? ORDER BY sort_order, value", (k,)).fetchall()
    conn.close()
    return render_template("lookups.html", data=data)


@app.route("/lookups/<field_key>/add", methods=["POST"])
@role_required("manager")
def lookup_add(field_key):
    db.add_lookup_value(field_key, request.form.get("value", ""))
    db.log_action(current_user()["username"], "lookup_add", f"{field_key}:{request.form.get('value','')}")
    return redirect(url_for("lookups_page"))


@app.route("/lookups/<int:lookup_id>/rename", methods=["POST"])
@role_required("manager")
def lookup_rename(lookup_id):
    db.rename_lookup_value(lookup_id, request.form.get("value", ""))
    db.log_action(current_user()["username"], "lookup_rename", f"lookup#{lookup_id}")
    return redirect(url_for("lookups_page"))


@app.route("/lookups/<int:lookup_id>/delete", methods=["POST"])
@role_required("manager")
def lookup_delete(lookup_id):
    db.delete_lookup_value(lookup_id)
    db.log_action(current_user()["username"], "lookup_delete", f"lookup#{lookup_id}")
    return redirect(url_for("lookups_page"))


# Inline "quick add" used by the dropdown widgets on asset forms (AJAX)
@app.route("/api/lookups/<field_key>/quick-add", methods=["POST"])
@role_required("editor")
def api_lookup_quick_add(field_key):
    value = (request.json or {}).get("value", "").strip()
    if value:
        db.add_lookup_value(field_key, value)
        db.log_action(current_user()["username"], "lookup_add", f"{field_key}:{value}")
    return jsonify({"values": db.get_lookup(field_key)})


# ---------------------------------------------------------------------------
# Diagram (Jira-Assets style link graph)
# ---------------------------------------------------------------------------

@app.route("/diagram")
@login_required
def diagram_page():
    return render_template("diagram.html")


def _node_key(table, row_id, is_sub=False):
    return f"{'sub' if is_sub else 'asset'}:{table}:{row_id}"


@app.route("/api/diagram/data")
@login_required
def api_diagram_data():
    positions = db.all_positions()
    links = db.list_links()
    nodes = {}
    edges = []

    def ensure_node(table, row_id):
        key = _node_key(table, row_id)
        if key in nodes:
            return key
        row = db.get_asset(table, row_id)
        if not row:
            return None
        x, y = positions.get(key, (None, None))
        nodes[key] = {
            "id": key, "table": table, "row_id": row_id,
            "label": db.asset_label(table, row),
            "group": table,
            "x": x, "y": y,
        }
        return key

    for link in links:
        sk = ensure_node(link["source_table"], link["source_id"])
        tk = ensure_node(link["target_table"], link["target_id"])
        if sk and tk:
            edges.append({
                "id": link["id"], "from": sk, "to": tk,
                "label": link["link_type"] or "",
                "notes": link["notes"] or "",
            })
    return jsonify({"nodes": list(nodes.values()), "edges": edges})


@app.route("/api/diagram/search-assets")
@login_required
def api_search_assets():
    q = request.args.get("q", "")
    return jsonify(db.search_all_assets(q) if q else [])


@app.route("/api/diagram/link", methods=["POST"])
@role_required("editor")
def api_create_link():
    data = request.json or {}
    db.create_link(
        data["source_table"], int(data["source_id"]),
        data["target_table"], int(data["target_id"]),
        data.get("link_type", "connected to"), data.get("label", ""),
        data.get("notes", ""), current_user()["username"])
    db.log_action(current_user()["username"], "link_create", f"{data['source_table']}#{data['source_id']} -> {data['target_table']}#{data['target_id']}")
    return jsonify({"ok": True})


@app.route("/api/diagram/link/<int:link_id>", methods=["DELETE"])
@role_required("editor")
def api_delete_link(link_id):
    db.delete_link(link_id)
    db.log_action(current_user()["username"], "link_delete", f"link#{link_id}")
    return jsonify({"ok": True})


@app.route("/api/diagram/position", methods=["POST"])
@role_required("editor")
def api_save_position():
    data = request.json or {}
    db.save_position(data["node_key"], data["x"], data["y"])
    db.log_action(current_user()["username"], "diagram_position_update", data["node_key"])
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Import / Export (CSV, Excel, Visio .vdx)
# ---------------------------------------------------------------------------

@app.route("/export/<table>.csv")
@login_required
def export_csv(table):
    if table not in db.SCHEMAS:
        abort(404)
    spec = db.SCHEMAS[table]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([f[1] for f in spec["fields"]])
    for row in db.list_assets(table):
        writer.writerow([row[f[0]] for f in spec["fields"]])
    mem = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                      download_name=f"{table}_{datetime.now():%Y%m%d_%H%M}.csv")


@app.route("/export/<table>.xlsx")
@login_required
def export_xlsx(table):
    if not EXCEL_AVAILABLE:
        flash("openpyxl is not installed.", "danger")
        return redirect(url_for("asset_list", table=table))
    if table not in db.SCHEMAS:
        abort(404)
    spec = db.SCHEMAS[table]
    wb = Workbook()
    ws = wb.active
    ws.title = spec["label"][:31]
    ws.append([f[1] for f in spec["fields"]])
    for row in db.list_assets(table):
        ws.append([row[f[0]] for f in spec["fields"]])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    mem = io.BytesIO()
    wb.save(mem)
    mem.seek(0)
    return send_file(mem, as_attachment=True,
                      download_name=f"{table}_{datetime.now():%Y%m%d_%H%M}.xlsx")


@app.route("/import/<table>", methods=["POST"])
@role_required("editor")
def import_table(table):
    if table not in db.SCHEMAS:
        abort(404)
    file = request.files.get("file")
    if not file:
        flash("No file selected.", "danger")
        return redirect(url_for("asset_list", table=table))
    try:
        filename = (file.filename or "").lower()
        if filename.endswith(".xlsx"):
            if not EXCEL_AVAILABLE:
                raise ValueError("Excel import requires openpyxl to be installed.")
            from openpyxl import load_workbook
            wb = load_workbook(file, read_only=True, data_only=True)
            ws = wb.active
            rows = [list(row) for row in ws.iter_rows(values_only=True)]
            wb.close()
            rows = [["" if value is None else str(value) for value in row] for row in rows]
        else:
            content = file.read().decode("utf-8-sig", errors="ignore")
            # Accept both comma-separated and semicolon-separated CSV files.
            sample = content[:4096]
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(io.StringIO(content), dialect)
            rows = list(reader)
        if not rows:
            raise ValueError("The file is empty.")
        headers = [str(h or "").strip() for h in rows[0]]
        mapping = db.match_import_columns(table, headers)
        if not any(mapping):
            raise ValueError("No matching columns found. Please check the header names.")
        imported = 0
        for values in rows[1:]:
            data = {}
            for idx, field in enumerate(mapping):
                if field and idx < len(values):
                    data[field] = str(values[idx] or "").strip()
            if any(data.values()):
                db.create_asset(table, data, current_user()["username"])
                imported += 1
        flash(f"{imported} record(s) imported successfully.", "success")
    except Exception as e:
        flash(f"Import error: {e}", "danger")
    return redirect(url_for("asset_list", table=table))


@app.route("/export/diagram.vdx")
@login_required
def export_diagram_vdx():
    positions = db.all_positions()
    links = db.list_links()
    nodes_by_key = {}

    def ensure(table, row_id):
        key = _node_key(table, row_id)
        if key not in nodes_by_key:
            row = db.get_asset(table, row_id)
            if not row:
                return None
            x, y = positions.get(key, (1 + len(nodes_by_key) * 2, 1))
            nodes_by_key[key] = {"key": key, "label": db.asset_label(table, row),
                                  "x": x or 1, "y": y or 1}
        return key

    edges = []
    for link in links:
        sk = ensure(link["source_table"], link["source_id"])
        tk = ensure(link["target_table"], link["target_id"])
        if sk and tk:
            edges.append({"source_key": sk, "target_key": tk, "label": link["link_type"]})

    vdx = visio_export.export_vdx(list(nodes_by_key.values()), edges)
    mem = io.BytesIO(vdx.encode("utf-8"))
    return send_file(mem, mimetype="application/xml", as_attachment=True,
                      download_name=f"diagram_{datetime.now():%Y%m%d_%H%M}.vdx")


@app.route("/import/diagram-vdx", methods=["POST"])
@role_required("editor")
def import_diagram_vdx():
    file = request.files.get("file")
    if not file:
        flash("No file selected.", "danger")
        return redirect(url_for("diagram_page"))
    shapes, _ = visio_export.import_vdx(file.read())
    matched = 0
    for shape in shapes:
        for table in db.SCHEMAS:
            for row in db.list_assets(table, shape["text"]):
                key = _node_key(table, row["id"])
                db.save_position(key, shape["x"], shape["y"])
                matched += 1
                break
    flash(f"{matched} shape(s) matched to existing assets and positions saved.", "info")
    return redirect(url_for("diagram_page"))


# ---------------------------------------------------------------------------
# Users (admin only) - 4 access levels: admin / manager / editor / viewer
# ---------------------------------------------------------------------------

@app.route("/logs/export.xlsx")
@role_required("manager")
def export_logs_xlsx():
    if not EXCEL_AVAILABLE:
        flash("openpyxl is not installed.", "danger")
        return redirect(url_for("logs_page", tab=request.args.get("tab", "audit")))
    tab = request.args.get("tab", "audit")
    if tab not in ("audit", "system"):
        tab = "audit"
    rows = db.list_audit_logs() if tab == "audit" else db.list_system_logs()
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit" if tab == "audit" else "System Log"
    ws.append(["ID", "Date / Time", "User", "Action", "Details"])
    for r in rows:
        ws.append([r["id"], r["created_at"], r["username"] or "system", r["action"], r["details"] or ""])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    widths = {"A": 10, "B": 22, "C": 24, "D": 30, "E": 90}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    for cell in ws[1]:
        cell.font = cell.font.copy(bold=True)
    mem = io.BytesIO()
    wb.save(mem)
    mem.seek(0)
    return send_file(mem, as_attachment=True,
                     download_name=f"{tab}_Log_{datetime.now():%Y%m%d_%H%M}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/logs")
@role_required("manager")
def logs_page():
    tab = request.args.get("tab", "audit")
    if tab not in ("audit", "system"):
        tab = "audit"
    return render_template("logs.html", tab=tab,
                           audit_logs=db.list_audit_logs(),
                           system_logs=db.list_system_logs())


@app.route("/users")
@role_required("admin")
def users_page():
    return render_template("users.html", users=db.list_users(), roles=db.ROLES)


@app.route("/users/new", methods=["POST"])
@role_required("admin")
def user_create():
    db.create_user(request.form["username"], request.form["password"],
                    request.form.get("full_name", ""), request.form.get("role", "viewer"))
    db.log_action(current_user()["username"], "user_create", request.form["username"])
    flash("User created successfully.", "success")
    return redirect(url_for("settings"))


@app.route("/users/<int:user_id>/edit", methods=["POST"])
@role_required("admin")
def user_edit(user_id):
    new_password = request.form.get("password") or None
    db.update_user(user_id, request.form.get("full_name", ""),
                    request.form.get("role", "viewer"),
                    1 if request.form.get("active") else 0, new_password)
    db.log_action(current_user()["username"], "user_update", f"user#{user_id}")
    if new_password:
        db.log_action(current_user()["username"], "user_password_change", f"user#{user_id}")
    flash("User updated successfully.", "success")
    return redirect(url_for("settings"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@role_required("admin")
def user_delete(user_id):
    db.delete_user(user_id)
    db.log_action(current_user()["username"], "user_delete", f"user#{user_id}")
    flash("User deleted successfully.", "warning")
    return redirect(url_for("settings"))


# Serve plain HTTP on :5000 by default for local development.
PORT = int(os.environ.get("FARBOD_ASSET_PORT", "5000"))
HOST = os.environ.get("FARBOD_ASSET_HOST", "127.0.0.1")
# Set FARBOD_ASSET_SSL=1 only when direct, self-signed local TLS is needed.
USE_SSL = os.environ.get("FARBOD_ASSET_SSL", "0") not in ("0", "false", "False", "")

CERT_DIR = os.path.join(BASE_DIR, "instance")
CERT_FILE = os.path.join(CERT_DIR, "cert.pem")
KEY_FILE = os.path.join(CERT_DIR, "key.pem")


def _ensure_self_signed_cert():
    """Create a self-signed TLS certificate on first run if one isn't already
    provided. Lets the app serve HTTPS directly on :443 with zero setup.
    Browsers will show a "not trusted" warning for this cert; that's expected
    for a self-signed certificate and can be replaced with a real one issued
    by your CA by dropping it at the same CERT_FILE/KEY_FILE paths."""
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        return True
    try:
        import datetime as _dt
        import ipaddress
        import socket
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        os.makedirs(CERT_DIR, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        hostname = socket.gethostname()
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])

        san = [x509.DNSName(u"localhost"), x509.DNSName(hostname)]
        # Include every local IPv4 address so direct HTTPS :443 also works
        # when clients connect with the server's LAN IP instead of its host name.
        local_ips = {"127.0.0.1"}
        try:
            for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
                local_ips.add(item[4][0])
        except Exception:
            pass
        for ip in sorted(local_ips):
            try:
                san.append(x509.IPAddress(ipaddress.IPv4Address(ip)))
            except Exception:
                pass

        now = _dt.datetime.utcnow()
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + _dt.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(key, hashes.SHA256())
        )

        with open(KEY_FILE, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))
        with open(CERT_FILE, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        return True
    except Exception:
        return False


def _startup_error(exc):
    try:
        root = paths.data_dir()
        os.makedirs(root, exist_ok=True)
        log_path = os.path.join(root, "startup.log")
        with open(log_path, "a", encoding="utf-8") as f:
            import traceback
            f.write("\n--- startup failure %s ---\n" % datetime.now().isoformat())
            traceback.print_exc(file=f)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        ssl_context = None
        if USE_SSL:
            if _ensure_self_signed_cert():
                ssl_context = (CERT_FILE, KEY_FILE)
            else:
                print("WARNING: could not create/find a TLS certificate; "
                      "falling back to plain HTTP. Set FARBOD_ASSET_SSL=0 to "
                      "silence this, or install the 'cryptography' package.")

        if ssl_context:
            # werkzeug's own server handles TLS termination directly, so the
            # The app can serve direct HTTPS for local testing when requested.
            from werkzeug.serving import run_simple
            run_simple(HOST, PORT, app, threaded=True, ssl_context=ssl_context,
                       use_reloader=False)
        else:
            debug = os.environ.get("FLASK_DEBUG", "0") in ("1", "true", "True")
            app.run(host=HOST, port=PORT, debug=debug, use_reloader=debug)
    except Exception as exc:
        _startup_error(exc)
        raise
