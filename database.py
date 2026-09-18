# -*- coding: utf-8 -*-
"""
Database layer for Farbod Asset Manager - Enterprise Web Edition.

Design goals:
- Pure sqlite3 (stdlib) -> zero external DB server, tiny footprint, easy to
  back up (single file). Can be pointed at a network share if a shared
  multi-user file is desired, or swapped for another DB later since all
  access goes through this module.
- Every "enum-like" field (Manufacturer, Status, Data Center, ...) is backed
  by a `lookups` table so values are editable/addable from the UI (dropdown
  + manage) instead of being hard coded.
- `asset_links` implements a generic graph: any asset (or sub-object) can be
  linked to any other asset/sub-object with a relationship type and label,
  which is what the Diagram view (Jira Assets / Insight style) renders.
- `sub_objects` lets an asset have child components (e.g. a Server's NICs,
  a Storage array's disk shelves) that can themselves be linked/diagrammed.
"""

import os
import sqlite3
import re
from datetime import datetime
from werkzeug.security import generate_password_hash

import paths

BASE_DIR = paths.data_dir()
DB_FILE = os.path.join(BASE_DIR, "instance", "dcam.db")

# ---------------------------------------------------------------------------
# Asset schemas (kept compatible with the original desktop tool's fields)
# Each field tuple: (key, label, type, dropdown_lookup_key_or_None)
# ---------------------------------------------------------------------------
SCHEMAS = {
    "servers": {
        "label": "Servers",
        "icon": "bi-server",
        "fields": [
            ("manufacturer", "Manufacturer", "text", "manufacturer"),
            ("model", "Model", "text", None),
            ("serial_number", "Serial Number", "text", None),
            ("asset_tag", "Asset Tag", "text", None),
            ("datacenter", "Data Center", "text", "datacenter"),
            ("room", "Room", "text", "room"),
            ("rack", "Rack", "text", "rack"),
            ("u_position", "U Position", "text", None),
            ("cpu", "CPU", "text", None),
            ("ram", "RAM", "text", None),
            ("disk", "Disk", "text", None),
            ("ETH Port1", "ETH Port1", "text", None),
            ("ETH Port2", "ETH Port2", "text", None),
            ("ETH Port3", "ETH Port3", "text", None),
            ("ETH Port4", "ETH Port4", "text", None),
            ("HBA1 Port1", "HBA1 Port1", "text", None),
            ("HBA1 Port2", "HBA1 Port2", "text", None),
            ("HBA2 Port1", "HBA2 Port1", "text", None),
            ("HBA2 Port2", "HBA2 Port2", "text", None),
            ("network_port1", "Network Port 1", "text", None),
            ("network_port2", "Network Port 2", "text", None),
            ("network_port3", "Network Port 3", "text", None),
            ("network_port4", "Network Port 4", "text", None),
            ("firmware", "Firmware", "text", None),
            ("ilo_ip", "iLO / iDRAC IP", "text", None),
            ("os", "Operating System", "text", "os"),
            ("hypervisor", "Hypervisor", "text", "hypervisor"),
            ("status", "Status", "text", "status"),
            ("notes", "Notes", "textarea", None),
        ],
    },
    "hpe_synergy_servers": {
        "label": "HPE Synergy Servers",
        "icon": "bi-server",
        "fields": [
            ("chassis_serial_number", "Chassis Serial Number", "text", None),
            ("ip1", "IP1", "text", None),
            ("ip2", "IP2", "text", None),
            ("ip3", "IP3", "text", None),
            ('compute_1_server_ip', 'Compute Module 1 - Server IP', 'text', None),
            ('compute_1_serial_number', 'Compute Module 1 - Serial Number', 'text', None),
            ('compute_1_hdd', 'Compute Module 1 - HDD', 'text', None),
            ('compute_1_notes', 'Compute Module 1 - Notes', 'textarea', None),
            ('compute_2_server_ip', 'Compute Module 2 - Server IP', 'text', None),
            ('compute_2_serial_number', 'Compute Module 2 - Serial Number', 'text', None),
            ('compute_2_hdd', 'Compute Module 2 - HDD', 'text', None),
            ('compute_2_notes', 'Compute Module 2 - Notes', 'textarea', None),
            ('compute_3_server_ip', 'Compute Module 3 - Server IP', 'text', None),
            ('compute_3_serial_number', 'Compute Module 3 - Serial Number', 'text', None),
            ('compute_3_hdd', 'Compute Module 3 - HDD', 'text', None),
            ('compute_3_notes', 'Compute Module 3 - Notes', 'textarea', None),
            ('compute_4_server_ip', 'Compute Module 4 - Server IP', 'text', None),
            ('compute_4_serial_number', 'Compute Module 4 - Serial Number', 'text', None),
            ('compute_4_hdd', 'Compute Module 4 - HDD', 'text', None),
            ('compute_4_notes', 'Compute Module 4 - Notes', 'textarea', None),
            ('compute_5_server_ip', 'Compute Module 5 - Server IP', 'text', None),
            ('compute_5_serial_number', 'Compute Module 5 - Serial Number', 'text', None),
            ('compute_5_hdd', 'Compute Module 5 - HDD', 'text', None),
            ('compute_5_notes', 'Compute Module 5 - Notes', 'textarea', None),
            ('compute_6_server_ip', 'Compute Module 6 - Server IP', 'text', None),
            ('compute_6_serial_number', 'Compute Module 6 - Serial Number', 'text', None),
            ('compute_6_hdd', 'Compute Module 6 - HDD', 'text', None),
            ('compute_6_notes', 'Compute Module 6 - Notes', 'textarea', None),
            ('compute_7_server_ip', 'Compute Module 7 - Server IP', 'text', None),
            ('compute_7_serial_number', 'Compute Module 7 - Serial Number', 'text', None),
            ('compute_7_hdd', 'Compute Module 7 - HDD', 'text', None),
            ('compute_7_notes', 'Compute Module 7 - Notes', 'textarea', None),
            ('compute_8_server_ip', 'Compute Module 8 - Server IP', 'text', None),
            ('compute_8_serial_number', 'Compute Module 8 - Serial Number', 'text', None),
            ('compute_8_hdd', 'Compute Module 8 - HDD', 'text', None),
            ('compute_8_notes', 'Compute Module 8 - Notes', 'textarea', None),
            ('compute_9_server_ip', 'Compute Module 9 - Server IP', 'text', None),
            ('compute_9_serial_number', 'Compute Module 9 - Serial Number', 'text', None),
            ('compute_9_hdd', 'Compute Module 9 - HDD', 'text', None),
            ('compute_9_notes', 'Compute Module 9 - Notes', 'textarea', None),
            ('compute_10_server_ip', 'Compute Module 10 - Server IP', 'text', None),
            ('compute_10_serial_number', 'Compute Module 10 - Serial Number', 'text', None),
            ('compute_10_hdd', 'Compute Module 10 - HDD', 'text', None),
            ('compute_10_notes', 'Compute Module 10 - Notes', 'textarea', None),
            ('compute_11_server_ip', 'Compute Module 11 - Server IP', 'text', None),
            ('compute_11_serial_number', 'Compute Module 11 - Serial Number', 'text', None),
            ('compute_11_hdd', 'Compute Module 11 - HDD', 'text', None),
            ('compute_11_notes', 'Compute Module 11 - Notes', 'textarea', None),
            ('compute_12_server_ip', 'Compute Module 12 - Server IP', 'text', None),
            ('compute_12_serial_number', 'Compute Module 12 - Serial Number', 'text', None),
            ('compute_12_hdd', 'Compute Module 12 - HDD', 'text', None),
            ('compute_12_notes', 'Compute Module 12 - Notes', 'textarea', None),
            ('icb_1_notes', 'ICB1 - Notes', 'textarea', None),
            ('icb_2_notes', 'ICB2 - Notes', 'textarea', None),
            ('icb_3_notes', 'ICB3 - Notes', 'textarea', None),
            ('icb_4_notes', 'ICB4 - Notes', 'textarea', None),
            ('icb_5_notes', 'ICB5 - Notes', 'textarea', None),
            ('icb_6_notes', 'ICB6 - Notes', 'textarea', None),
        ],
    },
    "storage": {
        "label": "Storage",
        "icon": "bi-hdd-rack",
        "fields": [
            ("manufacturer", "Manufacturer", "text", "manufacturer"),
            ("model", "Model", "text", None),
            ("serial_number", "Serial Number", "text", None),
            ("asset_tag", "Asset Tag", "text", None),
            ("datacenter", "Data Center", "text", "datacenter"),
            ("room", "Room", "text", "room"),
            ("rack", "Rack", "text", "rack"),
            ("controller", "Controller", "text", None),
            ("SPA_PORT_0", "SPA PORT 0", "text", None),
            ("SPA_PORT_1", "SPA PORT 1", "text", None),
            ("SPA_PORT_2", "SPA PORT 2", "text", None),
            ("SPA_PORT_3", "SPA PORT 3", "text", None),
            ("SPB_PORT_0", "SPB PORT 0", "text", None),
            ("SPB_PORT_1", "SPB PORT 1", "text", None),
            ("SPB_PORT_2", "SPB PORT 2", "text", None),
            ("SPB_PORT_3", "SPB PORT 3", "text", None),
            ("pool", "Pool", "text", None),
            ("management_ip", "Management IP", "text", None),
            ("firmware", "Firmware / OE", "text", None),
            ("status", "Status", "text", "status"),
            ("notes", "Notes", "textarea", None),
        ],
    },
    "san_switches": {
        "label": "SAN Switches",
        "icon": "bi-diagram-3",
        "fields": [
            ("manufacturer", "Manufacturer", "text", "manufacturer"),
            ("model", "Model", "text", None),
            ("serial_number", "Serial Number", "text", None),
            ("asset_tag", "Asset Tag", "text", None),
            ("datacenter", "Data Center", "text", "datacenter"),
            ("room", "Room", "text", "room"),
            ("rack", "Rack", "text", "rack"),
            ("wwn", "WWN", "text", None),
            ("fc_ports", "FC Ports", "text", None),
            ("fabric", "Fabric", "text", "fabric"),
            ("management_ip", "Management IP", "text", None),
            ("firmware", "Firmware", "text", None),
            ("status", "Status", "text", "status"),
            ("notes", "Notes", "textarea", None),
        ],
    },
    "network": {
        "label": "Network Devices",
        "icon": "bi-router",
        "fields": [
            ("device_type", "Device Type", "text", "device_type"),
            ("manufacturer", "Manufacturer", "text", "manufacturer"),
            ("model", "Model", "text", None),
            ("serial_number", "Serial Number", "text", None),
            ("asset_tag", "Asset Tag", "text", None),
            ("datacenter", "Data Center", "text", "datacenter"),
            ("room", "Room", "text", "room"),
            ("rack", "Rack", "text", "rack"),
            ("management_ip", "Management IP", "text", None),
            ("vlan", "VLAN", "text", None),
            ("firmware", "Firmware", "text", None),
            ("status", "Status", "text", "status"),
            ("notes", "Notes", "textarea", None),
        ],
    },
    "racks": {
        "label": "Racks",
        "icon": "bi-inboxes",
        "fields": [
            ("datacenter", "Data Center", "text", "datacenter"),
            ("room", "Room", "text", "room"),
            ("rack_number", "Rack Number", "text", None),
            ("rack_name", "Rack Name", "text", None),
            ("rack_size_u", "Rack Size (U)", "text", None),
            ("power", "Power", "text", None),
            ("notes", "Notes", "textarea", None),
        ],
    },
    "cables": {
        "label": "Cables",
        "icon": "bi-plug",
        "fields": [
            ("cable_type", "Cable Type", "text", "cable_type"),
            ("source_device", "Source Device", "text", None),
            ("source_port", "Source Port", "text", None),
            ("destination_device", "Destination Device", "text", None),
            ("destination_port", "Destination Port", "text", None),
            ("cable_label", "Cable Label", "text", None),
            ("status", "Status", "text", "status"),
            ("notes", "Notes", "textarea", None),
        ],
    },

    "esxi_hosts": {
        "label": "ESXi Hosts",
        "icon": "bi-cpu",
        "fields": [
            ("hostname", "Hostname", "text", None),
            ("cluster_name", "Cluster", "text", None),
            ("server_serial", "Server Serial", "text", None),
            ("management_ip", "Management IP", "text", None),
            ("esxi_version", "ESXi Version", "text", None),
            ("status", "Status", "text", "status"),
            ("notes", "Notes", "textarea", None),
        ],
    },


}

# Default seed values for dropdown lookups (all editable later in the UI)
DEFAULT_LOOKUPS = {
    "manufacturer": ["HPE", "Dell", "Cisco", "NetApp", "IBM", "Huawei", "Lenovo"],
    "status": ["Active", "Standby", "Maintenance", "Decommissioned", "Faulty"],
    "datacenter": ["DC-1", "DC-2"],
    "room": ["Room-101", "Room-102"],
    "rack": [],
    "os": ["Windows Server 2022", "RHEL 9", "Ubuntu 22.04", "ESXi 8.0"],
    "hypervisor": ["VMware ESXi", "Hyper-V", "KVM", "None"],
    "device_type": ["Switch", "Router", "Firewall", "Load Balancer"],
    "cable_type": ["Fiber LC-LC", "Fiber SC-LC", "Copper Cat6", "DAC"],
    "fabric": ["Fabric-A", "Fabric-B"],
}

ROLES = ["admin", "manager", "operator"]
ROLE_LEVEL = {"operator": 0, "manager": 2, "admin": 3, "editor": 2}


def get_conn():
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    first_run = not os.path.exists(DB_FILE)
    conn = get_conn()
    cur = conn.cursor()

    for table, spec in SCHEMAS.items():
        cols = ", ".join(f'"{f[0]}" TEXT' for f in spec["fields"])
        cur.execute(f'''
            CREATE TABLE IF NOT EXISTS "{table}" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                {cols},
                created_at TEXT,
                updated_at TEXT
            )
        ''')

        # Migrate databases created by older builds.  CREATE TABLE IF NOT EXISTS
        # does not add new columns, which previously caused 500 errors when an
        # existing database was opened by a newer EXE.
        existing = {row[1] for row in cur.execute(f'PRAGMA table_info("{table}")').fetchall()}
        for field_key, _label, _ftype, _lookup in spec["fields"]:
            if field_key not in existing:
                cur.execute(f'ALTER TABLE "{table}" ADD COLUMN "{field_key}" TEXT')
        existing = {row[1] for row in cur.execute(f'PRAGMA table_info("{table}")').fetchall()}
        if "created_at" not in existing:
            cur.execute(f'ALTER TABLE "{table}" ADD COLUMN created_at TEXT')
        if "updated_at" not in existing:
            cur.execute(f'ALTER TABLE "{table}" ADD COLUMN updated_at TEXT')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS lookups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_key TEXT NOT NULL,
            value TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            UNIQUE(field_key, value)
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS sub_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_table TEXT NOT NULL,
            parent_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            obj_type TEXT,
            notes TEXT,
            created_at TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS asset_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_table TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            target_table TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            link_type TEXT DEFAULT 'connected to',
            label TEXT,
            notes TEXT,
            created_by TEXT,
            created_at TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS diagram_positions (
            node_key TEXT PRIMARY KEY,
            x REAL,
            y REAL
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            role TEXT NOT NULL DEFAULT 'viewer',
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS module_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_key TEXT NOT NULL,
            username TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    ''')

    # Upgrade old single-user-per-module schema by rebuilding it without UNIQUE(module_key).
    idxs = cur.execute("PRAGMA index_list(module_users)").fetchall()
    if any(i[2] and [r[2] for r in cur.execute(f'PRAGMA index_info("{i[1]}")').fetchall()] == ["module_key"] for i in idxs):
        cur.execute("ALTER TABLE module_users RENAME TO module_users_old")
        cur.execute("CREATE TABLE module_users (id INTEGER PRIMARY KEY AUTOINCREMENT, module_key TEXT NOT NULL, username TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER DEFAULT 1, created_at TEXT, UNIQUE(module_key, username))")
        cur.execute("INSERT INTO module_users SELECT id,module_key,username,password_hash,active,created_at FROM module_users_old")
        cur.execute("DROP TABLE module_users_old")

    cur.execute('''
        CREATE TABLE IF NOT EXISTS equipment_banks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS equipment_bank_subcategories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bank_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT,
            UNIQUE(bank_id, name),
            FOREIGN KEY(bank_id) REFERENCES equipment_banks(id) ON DELETE CASCADE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS equipment_bank_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subcategory_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            media_type TEXT NOT NULL,
            size_bytes INTEGER,
            uploaded_by TEXT,
            created_at TEXT,
            FOREIGN KEY(subcategory_id) REFERENCES equipment_bank_subcategories(id) ON DELETE CASCADE
        )
    ''')
    equipment_file_cols = {r[1] for r in cur.execute('PRAGMA table_info("equipment_bank_files")').fetchall()}
    if "description" not in equipment_file_cols:
        cur.execute("ALTER TABLE equipment_bank_files ADD COLUMN description TEXT DEFAULT ''")

    cur.execute('''
        CREATE TABLE IF NOT EXISTS bank_connection_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            media_type TEXT NOT NULL,
            size_bytes INTEGER,
            uploaded_by TEXT,
            description TEXT NOT NULL,
            created_at TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS sub_object_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sub_object_id INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            media_type TEXT NOT NULL,
            size_bytes INTEGER,
            uploaded_by TEXT,
            description TEXT NOT NULL,
            created_at TEXT,
            FOREIGN KEY(sub_object_id) REFERENCES sub_objects(id) ON DELETE CASCADE
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            size_bytes INTEGER,
            media_type TEXT,
            uploaded_by TEXT,
            created_at TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_presence (
            username TEXT PRIMARY KEY,
            session_id TEXT,
            last_seen TEXT NOT NULL,
            ip_address TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            details TEXT,
            created_at TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS system_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            details TEXT,
            created_at TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS monitoring_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            device_type TEXT NOT NULL DEFAULT 'HPE iLO',
            management_ip TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL,
            password_enc TEXT NOT NULL,
            verify_ssl INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Pending',
            vendor TEXT DEFAULT 'HPE',
            model TEXT,
            serial_number TEXT,
            firmware TEXT,
            last_error TEXT,
            last_seen TEXT,
            created_by TEXT,
            created_at TEXT
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS iso_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL UNIQUE,
            size_bytes INTEGER,
            notes TEXT,
            uploaded_by TEXT,
            created_at TEXT,
            media_type TEXT DEFAULT 'iso'
        )
    ''')
    # Migrate older installations that did not have a media_type column.
    media_cols = {r[1] for r in cur.execute('PRAGMA table_info("iso_files")').fetchall()}
    if "media_type" not in media_cols:
        cur.execute("ALTER TABLE iso_files ADD COLUMN media_type TEXT DEFAULT 'iso'")

    # Normalize legacy roles to the new AI-Hub access model.
    cur.execute("UPDATE users SET role='manager' WHERE role='editor'")
    cur.execute("UPDATE users SET role='operator' WHERE role='viewer'")
    conn.commit()

    # Farbod AI-Hub predefined Equipment workspaces. Existing user-created banks are preserved.
    for bank_name in ('Pasargad bank','Taavon bank','Dotin','Resalat bank','Refah bank','Karafarin bank','Gardeshgari bank','Riton'):
        cur.execute("INSERT OR IGNORE INTO equipment_banks(name,created_at) VALUES(?,?)", (bank_name, datetime.now().isoformat()))
    conn.commit()

    if first_run:
        for key, values in DEFAULT_LOOKUPS.items():
            for i, v in enumerate(values):
                cur.execute(
                    "INSERT OR IGNORE INTO lookups (field_key, value, sort_order) VALUES (?,?,?)",
                    (key, v, i))
        conn.commit()

        cur.execute(
            "INSERT INTO users (username, password_hash, full_name, role, active, created_at) "
            "VALUES (?,?,?,?,1,?)",
            ("admin", generate_password_hash("admin123"), "Administrator",
             "admin", datetime.now().isoformat()))
        conn.commit()

    module_defaults = [
        ("asset_manager", "asset", "Asset@2026"),
        ("knowledge", "knowledge", "Knowledge@2026"),
        ("equipment_profile", "equipment", "Equipment@2026"),
        ("settings", "settings", "Setting@2026"),
    ]
    for module_key, username, password in module_defaults:
        cur.execute(
            "INSERT OR IGNORE INTO module_users "
            "(module_key, username, password_hash, active, created_at) VALUES (?,?,?,?,?)",
            (module_key, username, generate_password_hash(password), 1, datetime.now().isoformat())
        )
    conn.commit()

    conn.close()


def get_module_user(module_key, username=None):
    conn = get_conn()
    if username:
        row = conn.execute("SELECT * FROM module_users WHERE module_key=? AND username=?", (module_key, username)).fetchone()
    else:
        row = conn.execute("SELECT * FROM module_users WHERE module_key=? ORDER BY id LIMIT 1", (module_key,)).fetchone()
    conn.close(); return row

def list_module_users(module_key):
    conn = get_conn(); rows = conn.execute("SELECT id,module_key,username,active,created_at FROM module_users WHERE module_key=? ORDER BY username", (module_key,)).fetchall(); conn.close(); return rows

def create_module_user(module_key, username, password):
    conn=get_conn(); conn.execute("INSERT INTO module_users(module_key,username,password_hash,active,created_at) VALUES(?,?,?,?,?)",(module_key,username,generate_password_hash(password),1,datetime.now().isoformat())); conn.commit(); conn.close()

def update_module_user(user_id,module_key,username,password=None,active=1):
    conn=get_conn()
    if password: conn.execute("UPDATE module_users SET username=?,password_hash=?,active=? WHERE id=? AND module_key=?",(username,generate_password_hash(password),active,user_id,module_key))
    else: conn.execute("UPDATE module_users SET username=?,active=? WHERE id=? AND module_key=?",(username,active,user_id,module_key))
    conn.commit(); conn.close()

def delete_module_user(user_id,module_key):
    conn=get_conn(); conn.execute("DELETE FROM module_users WHERE id=? AND module_key=?",(user_id,module_key)); conn.commit(); conn.close()

def update_module_credentials(module_key, username, password=None):
    user=get_module_user(module_key)
    if user: update_module_user(user["id"],module_key,username,password,user["active"])

def list_equipment_banks():
    conn=get_conn(); rows=conn.execute("SELECT * FROM equipment_banks ORDER BY name COLLATE NOCASE").fetchall(); conn.close(); return rows

def get_equipment_bank(bank_id):
    conn=get_conn(); row=conn.execute("SELECT * FROM equipment_banks WHERE id=?", (bank_id,)).fetchone(); conn.close(); return row

def list_equipment_subcategories(bank_id):
    conn=get_conn(); rows=conn.execute("SELECT * FROM equipment_bank_subcategories WHERE bank_id=? ORDER BY name COLLATE NOCASE",(bank_id,)).fetchall(); conn.close(); return rows

def get_equipment_subcategory(sub_id):
    conn=get_conn(); row=conn.execute("SELECT * FROM equipment_bank_subcategories WHERE id=?", (sub_id,)).fetchone(); conn.close(); return row

def create_equipment_bank(name):
    conn=get_conn(); cur=conn.execute("INSERT INTO equipment_banks(name,created_at) VALUES(?,?)",(name,datetime.now().isoformat())); conn.commit(); row=conn.execute("SELECT * FROM equipment_banks WHERE id=?",(cur.lastrowid,)).fetchone(); conn.close(); return row

def delete_equipment_bank(bank_id):
    """Delete an equipment bank and its subcategories/files, including stored files on disk."""
    conn=get_conn()
    file_rows=conn.execute(
        "SELECT stored_name FROM equipment_bank_files WHERE subcategory_id IN "
        "(SELECT id FROM equipment_bank_subcategories WHERE bank_id=?)", (bank_id,)
    ).fetchall()
    conn.execute("DELETE FROM equipment_bank_files WHERE subcategory_id IN (SELECT id FROM equipment_bank_subcategories WHERE bank_id=?)", (bank_id,))
    conn.execute("DELETE FROM equipment_bank_subcategories WHERE bank_id=?", (bank_id,))
    conn.execute("DELETE FROM equipment_banks WHERE id=?", (bank_id,))
    conn.commit(); conn.close()
    return [r[0] for r in file_rows]

def create_equipment_subcategory(bank_id,name):
    conn=get_conn(); cur=conn.execute("INSERT INTO equipment_bank_subcategories(bank_id,name,created_at) VALUES(?,?,?)",(bank_id,name,datetime.now().isoformat())); conn.commit(); row=conn.execute("SELECT * FROM equipment_bank_subcategories WHERE id=?",(cur.lastrowid,)).fetchone(); conn.close(); return row

def list_equipment_files(sub_id):
    conn=get_conn(); rows=conn.execute("SELECT * FROM equipment_bank_files WHERE subcategory_id=? ORDER BY id DESC",(sub_id,)).fetchall(); conn.close(); return rows

def add_equipment_file(sub_id, original_name, stored_name, media_type, size_bytes, uploaded_by, description=""):
    conn=get_conn(); cur=conn.execute("INSERT INTO equipment_bank_files(subcategory_id,original_name,stored_name,media_type,size_bytes,uploaded_by,created_at,description) VALUES(?,?,?,?,?,?,?,?)",(sub_id,original_name,stored_name,media_type,size_bytes,uploaded_by,datetime.now().isoformat(),description)); conn.commit(); row=conn.execute("SELECT * FROM equipment_bank_files WHERE id=?",(cur.lastrowid,)).fetchone(); conn.close(); return row

def list_bank_connection_files():
    conn=get_conn(); rows=conn.execute("SELECT * FROM bank_connection_files ORDER BY id DESC").fetchall(); conn.close(); return rows

def add_bank_connection_file(original_name, stored_name, media_type, size_bytes, uploaded_by, description):
    conn=get_conn(); cur=conn.execute("INSERT INTO bank_connection_files(original_name,stored_name,media_type,size_bytes,uploaded_by,description,created_at) VALUES(?,?,?,?,?,?,?)",(original_name,stored_name,media_type,size_bytes,uploaded_by,description,datetime.now().isoformat())); conn.commit(); row=conn.execute("SELECT * FROM bank_connection_files WHERE id=?",(cur.lastrowid,)).fetchone(); conn.close(); return row

def get_bank_connection_file(file_id):
    conn=get_conn(); row=conn.execute("SELECT * FROM bank_connection_files WHERE id=?",(file_id,)).fetchone(); conn.close(); return row

def get_sub_object(sub_id):
    conn=get_conn(); row=conn.execute("SELECT * FROM sub_objects WHERE id=?",(sub_id,)).fetchone(); conn.close(); return row

def list_sub_object_files(sub_id):
    conn=get_conn(); rows=conn.execute("SELECT * FROM sub_object_files WHERE sub_object_id=? ORDER BY id DESC",(sub_id,)).fetchall(); conn.close(); return rows

def add_sub_object_file(sub_id, original_name, stored_name, media_type, size_bytes, uploaded_by, description):
    conn=get_conn(); cur=conn.execute("INSERT INTO sub_object_files(sub_object_id,original_name,stored_name,media_type,size_bytes,uploaded_by,description,created_at) VALUES(?,?,?,?,?,?,?,?)",(sub_id,original_name,stored_name,media_type,size_bytes,uploaded_by,description,datetime.now().isoformat())); conn.commit(); row=conn.execute("SELECT * FROM sub_object_files WHERE id=?",(cur.lastrowid,)).fetchone(); conn.close(); return row

def get_sub_object_file(file_id):
    conn=get_conn(); row=conn.execute("SELECT * FROM sub_object_files WHERE id=?",(file_id,)).fetchone(); conn.close(); return row

def get_equipment_file(file_id):
    conn=get_conn(); row=conn.execute("SELECT * FROM equipment_bank_files WHERE id=?",(file_id,)).fetchone(); conn.close(); return row

def list_knowledge_files(category):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM knowledge_files WHERE category=? ORDER BY id DESC", (category,)
    ).fetchall()
    conn.close()
    return rows


def add_knowledge_file(category, original_name, stored_name, description,
                        size_bytes, media_type, uploaded_by):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO knowledge_files "
        "(category, original_name, stored_name, description, size_bytes, media_type, uploaded_by, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (category, original_name, stored_name, description, size_bytes, media_type,
         uploaded_by, datetime.now().isoformat())
    )
    conn.commit()
    row = conn.execute("SELECT * FROM knowledge_files WHERE id=?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row


def get_knowledge_file(file_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM knowledge_files WHERE id=?", (file_id,)).fetchone()
    conn.close()
    return row


# ---------------------------------------------------------------------------
# Generic asset CRUD (table-driven off SCHEMAS)
# ---------------------------------------------------------------------------

def list_assets(table, q=None):
    spec = SCHEMAS[table]
    conn = get_conn()
    if q:
        like = f"%{q}%"
        clauses = " OR ".join(f'"{f[0]}" LIKE ?' for f in spec["fields"])
        rows = conn.execute(
            f'SELECT * FROM "{table}" WHERE {clauses} ORDER BY id ASC',
            [like] * len(spec["fields"])).fetchall()
    else:
        rows = conn.execute(f'SELECT * FROM "{table}" ORDER BY id ASC').fetchall()
    conn.close()
    return rows


def get_asset(table, row_id):
    conn = get_conn()
    row = conn.execute(f'SELECT * FROM "{table}" WHERE id=?', (row_id,)).fetchone()
    conn.close()
    return row


def create_asset(table, data, username=None):
    spec = SCHEMAS[table]
    keys = [f[0] for f in spec["fields"]]
    now = datetime.now().isoformat()
    values = [data.get(k, "").strip() for k in keys]
    placeholders = ",".join(["?"] * (len(keys) + 2))
    cols = ",".join(f'"{k}"' for k in keys) + ", created_at, updated_at"
    conn = get_conn()
    cur = conn.execute(
        f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})',
        values + [now, now])
    conn.commit()
    new_id = cur.lastrowid
    log_action(username, "create", f"{table}#{new_id}")
    conn.close()
    return new_id


def update_asset(table, row_id, data, username=None):
    spec = SCHEMAS[table]
    keys = [f[0] for f in spec["fields"]]
    now = datetime.now().isoformat()
    set_clause = ", ".join(f'"{k}"=?' for k in keys) + ', updated_at=?'
    values = [data.get(k, "").strip() for k in keys] + [now, row_id]
    conn = get_conn()
    conn.execute(f'UPDATE "{table}" SET {set_clause} WHERE id=?', values)
    conn.commit()
    conn.close()
    log_action(username, "update", f"{table}#{row_id}")


def delete_asset(table, row_id, username=None):
    conn = get_conn()
    conn.execute(f'DELETE FROM "{table}" WHERE id=?', (row_id,))
    conn.execute('DELETE FROM asset_links WHERE (source_table=? AND source_id=?) '
                 'OR (target_table=? AND target_id=?)', (table, row_id, table, row_id))
    conn.execute('DELETE FROM sub_objects WHERE parent_table=? AND parent_id=?', (table, row_id))
    conn.commit()
    conn.close()
    log_action(username, "delete", f"{table}#{row_id}")

def delete_assets(table, row_ids, username=None):
    if table not in SCHEMAS: raise ValueError("Unknown asset table")
    ids=sorted(set(int(x) for x in row_ids if int(x)>0))
    if not ids: return 0
    conn=get_conn()
    try:
        for row_id in ids:
            conn.execute('DELETE FROM asset_links WHERE (source_table=? AND source_id=?) OR (target_table=? AND target_id=?)',(table,row_id,table,row_id))
            subs=conn.execute("SELECT id FROM sub_objects WHERE parent_table=? AND parent_id=?",(table,row_id)).fetchall()
            for sub in subs: conn.execute("DELETE FROM sub_object_files WHERE sub_object_id=?",(sub[0],))
            conn.execute("DELETE FROM sub_objects WHERE parent_table=? AND parent_id=?",(table,row_id))
        ph=",".join("?" for _ in ids); deleted=conn.execute(f'DELETE FROM "{table}" WHERE id IN ({ph})',ids).rowcount; conn.commit()
    finally: conn.close()
    for row_id in ids: log_action(username,"delete",f"{table}#{row_id}")
    return deleted


# ---------------------------------------------------------------------------
# Lookups (dropdown values, editable from the UI)
# ---------------------------------------------------------------------------

def get_lookup(field_key):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM lookups WHERE field_key=? ORDER BY sort_order, value",
        (field_key,)).fetchall()
    conn.close()
    return [r["value"] for r in rows]


def all_lookup_keys():
    keys = set()
    for spec in SCHEMAS.values():
        for f in spec["fields"]:
            if f[3]:
                keys.add(f[3])
    return sorted(keys)


def add_lookup_value(field_key, value):
    value = value.strip()
    if not value:
        return
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO lookups (field_key, value, sort_order) VALUES (?,?,999)",
        (field_key, value))
    conn.commit()
    conn.close()


def rename_lookup_value(lookup_id, new_value):
    conn = get_conn()
    conn.execute("UPDATE lookups SET value=? WHERE id=?", (new_value.strip(), lookup_id))
    conn.commit()
    conn.close()


def delete_lookup_value(lookup_id):
    conn = get_conn()
    conn.execute("DELETE FROM lookups WHERE id=?", (lookup_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# ISO files (installation media the team keeps handy for server builds)
# ---------------------------------------------------------------------------

def list_iso_files():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM iso_files ORDER BY id ASC").fetchall()
    conn.close()
    return rows


def get_iso_file(iso_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM iso_files WHERE id=?", (iso_id,)).fetchone()
    conn.close()
    return row


def add_iso_file(original_name, stored_name, size_bytes, notes, uploaded_by, media_type="iso"):
    conn = get_conn()
    conn.execute(
        "INSERT INTO iso_files (original_name, stored_name, size_bytes, notes, uploaded_by, created_at, media_type) "
        "VALUES (?,?,?,?,?,?,?)",
        (original_name, stored_name, size_bytes, notes, uploaded_by,
         datetime.now().isoformat(), media_type))
    conn.commit()
    conn.close()


def delete_iso_file(iso_id):
    conn = get_conn()
    conn.execute("DELETE FROM iso_files WHERE id=?", (iso_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Sub-objects (components that belong to an asset, e.g. NIC, PSU, Disk Shelf)
# ---------------------------------------------------------------------------

def list_sub_objects(parent_table, parent_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM sub_objects WHERE parent_table=? AND parent_id=? ORDER BY id",
        (parent_table, parent_id)).fetchall()
    conn.close()
    return rows


def add_sub_object(parent_table, parent_id, name, obj_type, notes):
    conn = get_conn()
    conn.execute(
        "INSERT INTO sub_objects (parent_table, parent_id, name, obj_type, notes, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (parent_table, parent_id, name, obj_type, notes, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def delete_sub_object(sub_id):
    conn = get_conn()
    conn.execute("DELETE FROM sub_object_files WHERE sub_object_id=?", (sub_id,))
    conn.execute("DELETE FROM sub_objects WHERE id=?", (sub_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Asset links / diagram (Jira Assets style relationship graph)
# ---------------------------------------------------------------------------

def create_link(source_table, source_id, target_table, target_id, link_type, label, notes, username):
    conn = get_conn()
    conn.execute(
        "INSERT INTO asset_links (source_table, source_id, target_table, target_id, "
        "link_type, label, notes, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (source_table, source_id, target_table, target_id, link_type, label, notes,
         username, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def delete_link(link_id):
    conn = get_conn()
    conn.execute("DELETE FROM asset_links WHERE id=?", (link_id,))
    conn.commit()
    conn.close()


def list_links():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM asset_links").fetchall()
    conn.close()
    return rows


def links_for(table, row_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM asset_links WHERE (source_table=? AND source_id=?) "
        "OR (target_table=? AND target_id=?)", (table, row_id, table, row_id)).fetchall()
    conn.close()
    return rows


def save_position(node_key, x, y):
    conn = get_conn()
    conn.execute(
        "INSERT INTO diagram_positions (node_key, x, y) VALUES (?,?,?) "
        "ON CONFLICT(node_key) DO UPDATE SET x=excluded.x, y=excluded.y",
        (node_key, x, y))
    conn.commit()
    conn.close()


def all_positions():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM diagram_positions").fetchall()
    conn.close()
    return {r["node_key"]: (r["x"], r["y"]) for r in rows}


def asset_label(table, row):
    """Best-effort human readable label for a row (used as diagram node text)."""
    for key in ("hostname", "vm_name", "cluster_name", "datastore_name",
                "rack_name", "cable_label", "asset_tag", "model", "serial_number"):
        if key in row.keys() and row[key]:
            return row[key]
    return f"{SCHEMAS[table]['label']} #{row['id']}"


def search_all_assets(q):
    """Used by the diagram 'link picker' to find any asset across all tables."""
    like = f"%{q}%"
    results = []
    conn = get_conn()
    for table, spec in SCHEMAS.items():
        clauses = " OR ".join(f'"{f[0]}" LIKE ?' for f in spec["fields"])
        rows = conn.execute(
            f'SELECT * FROM "{table}" WHERE {clauses} ORDER BY id ASC LIMIT 15',
            [like] * len(spec["fields"])).fetchall()
        for r in rows:
            results.append({"table": table, "id": r["id"], "label": asset_label(table, r)})
    conn.close()
    return results


# ---------------------------------------------------------------------------
# Users / RBAC
# ---------------------------------------------------------------------------

def get_user(username):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return row


def list_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return rows


def create_user(username, password, full_name, role):
    conn = get_conn()
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, role, active, created_at) "
        "VALUES (?,?,?,?,1,?)",
        (username, generate_password_hash(password), full_name, role, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def update_user(user_id, full_name, role, active, new_password=None):
    conn = get_conn()
    if new_password:
        conn.execute(
            "UPDATE users SET full_name=?, role=?, active=?, password_hash=? WHERE id=?",
            (full_name, role, active, generate_password_hash(new_password), user_id))
    else:
        conn.execute(
            "UPDATE users SET full_name=?, role=?, active=? WHERE id=?",
            (full_name, role, active, user_id))
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()


def log_action(username, action, details):
    """Write every change to System Log and user/security events to Audit Log."""
    actor = username or "system"
    now = datetime.now().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO system_log (username, action, details, created_at) VALUES (?,?,?,?)",
        (actor, action, details, now))
    audit_actions = {"login", "logout", "user_create", "user_update", "user_delete", "user_password_change", "user_activate", "user_deactivate"}
    if action in audit_actions:
        conn.execute(
            "INSERT INTO audit_log (username, action, details, created_at) VALUES (?,?,?,?)",
            (actor, action, details, now))
    conn.commit()
    conn.close()

def list_audit_logs(limit=500):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    conn.close()
    return rows

def list_system_logs(limit=1000):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM system_log ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    conn.close()
    return rows


def normalize_header(value):
    value = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def match_import_columns(table, headers):
    spec = SCHEMAS[table]
    aliases = {}
    for key, label, *_ in spec["fields"]:
        aliases[normalize_header(key)] = key
        aliases[normalize_header(label)] = key
    return [aliases.get(normalize_header(h)) for h in headers]


# ---------------------------------------------------------------------------
# Live user presence
# ---------------------------------------------------------------------------
def touch_presence(username, session_id, ip_address=None):
    now = datetime.now().isoformat()
    conn = get_conn()
    conn.execute("""INSERT INTO user_presence (username, session_id, last_seen, ip_address)
                 VALUES (?,?,?,?)
                 ON CONFLICT(username) DO UPDATE SET
                   session_id=excluded.session_id, last_seen=excluded.last_seen, ip_address=excluded.ip_address""",
                 (username, session_id, now, ip_address))
    conn.commit(); conn.close()

def remove_presence(username, session_id=None):
    conn = get_conn()
    if session_id:
        conn.execute("DELETE FROM user_presence WHERE username=? AND session_id=?", (username, session_id))
    else:
        conn.execute("DELETE FROM user_presence WHERE username=?", (username,))
    conn.commit(); conn.close()

def online_users(timeout_seconds=90):
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(seconds=timeout_seconds)).isoformat()
    conn = get_conn()
    rows = conn.execute("""SELECT u.username, u.full_name, u.role, p.last_seen
                           FROM user_presence p JOIN users u ON u.username=p.username
                           WHERE p.last_seen >= ? AND u.active=1
                           ORDER BY COALESCE(u.full_name,u.username)""", (cutoff,)).fetchall()
    conn.execute("DELETE FROM user_presence WHERE last_seen < ?", (cutoff,))
    conn.commit(); conn.close()
    return rows


# --- Monitoring device registry -------------------------------------------------
def list_monitoring_devices():
    conn=get_conn(); rows=conn.execute("SELECT * FROM monitoring_devices ORDER BY id DESC").fetchall(); conn.close(); return rows

def get_monitoring_device(device_id):
    conn=get_conn(); row=conn.execute("SELECT * FROM monitoring_devices WHERE id=?",(device_id,)).fetchone(); conn.close(); return row

def create_monitoring_device(name, device_type, ip, username, password_enc, verify_ssl, created_by):
    conn=get_conn(); cur=conn.execute("INSERT INTO monitoring_devices(name,device_type,management_ip,username,password_enc,verify_ssl,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)",(name,device_type,ip,username,password_enc,1 if verify_ssl else 0,created_by,datetime.now().isoformat())); conn.commit(); did=cur.lastrowid; conn.close(); return did

def update_monitoring_device_status(device_id, **fields):
    allowed={'status','vendor','model','serial_number','firmware','last_error','last_seen'}; fields={k:v for k,v in fields.items() if k in allowed}
    if not fields:return
    conn=get_conn(); conn.execute("UPDATE monitoring_devices SET "+", ".join(f'{k}=?' for k in fields)+" WHERE id=?",list(fields.values())+[device_id]); conn.commit(); conn.close()

def delete_monitoring_device(device_id):
    conn=get_conn(); conn.execute("DELETE FROM monitoring_devices WHERE id=?",(device_id,)); conn.commit(); conn.close()
