#!/usr/bin/env python3
"""
HotelHub Server — Flask + SQLite
Lancez ce fichier pour démarrer le serveur.
"""
import os, sys, json, hashlib, threading, webbrowser, socket
from datetime import datetime
from flask import Flask, request, jsonify, send_file, abort

# ── Paths ──────────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# On Railway/cloud: use /data if exists, else BASE_DIR
_data_dir = "/data" if os.path.isdir("/data") else BASE_DIR
DB_PATH   = os.path.join(_data_dir, "hotelhub.db")
HTML_FILE = os.path.join(BASE_DIR, "hotelhub.html")
import os as _os
PORT      = int(_os.environ.get("PORT", 8766))

# ── Flask app ──────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── SQLite via raw sqlite3 (no deps) ──────────────────────────────────────
import sqlite3

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # concurrent reads
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def uid():
    import uuid
    return str(uuid.uuid4())[:8]

# ── DB Init ────────────────────────────────────────────────────────────────
def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'reception',
        active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS permissions (
        role TEXT NOT NULL,
        module TEXT NOT NULL,
        allowed INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (role, module)
    );
    CREATE TABLE IF NOT EXISTS locations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS staff (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        color TEXT NOT NULL DEFAULT '#388bfd'
    );
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        interval TEXT NOT NULL DEFAULT 'monthly',
        location_scope TEXT NOT NULL DEFAULT 'all'
    );
    CREATE TABLE IF NOT EXISTS checks (
        check_key TEXT PRIMARY KEY,
        loc_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        period_key TEXT NOT NULL,
        done_date TEXT,
        staff_id TEXT,
        staff_name TEXT,
        staff_color TEXT,
        done_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS history (
        id TEXT PRIMARY KEY,
        done_date TEXT,
        staff_id TEXT,
        staff_name TEXT,
        staff_color TEXT,
        loc_id TEXT,
        loc_name TEXT,
        task_id TEXT,
        task_name TEXT,
        ts INTEGER
    );
    CREATE TABLE IF NOT EXISTS interventions (
        id TEXT PRIMARY KEY,
        loc_id TEXT,
        loc_name TEXT,
        date TEXT,
        description TEXT,
        reported_by TEXT,
        assigned_to TEXT,
        status TEXT DEFAULT 'En cours',
        resolved_date TEXT,
        comment TEXT,
        created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS inventory_items (
        id TEXT PRIMARY KEY,
        inv_type TEXT NOT NULL,
        name TEXT NOT NULL,
        category TEXT,
        qty REAL DEFAULT 0,
        min_qty REAL DEFAULT 0,
        unit TEXT DEFAULT 'unité'
    );
    CREATE TABLE IF NOT EXISTS inventory_movements (
        id TEXT PRIMARY KEY,
        inv_type TEXT NOT NULL,
        item_id TEXT NOT NULL,
        item_name TEXT,
        move_type TEXT NOT NULL,
        qty REAL NOT NULL,
        by_user TEXT,
        move_date TEXT,
        note TEXT,
        ts INTEGER
    );
    """)

    # Seed default data if empty
    cur = db.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        default_users = [
            (uid(), "Administrateur",   "admin",     hash_pw("admin123"),   "admin",     1),
            (uid(), "Réception",        "reception", hash_pw("recep123"),   "reception", 1),
            (uid(), "Étage",            "etage",     hash_pw("etage123"),   "etage",     1),
            (uid(), "Technicien",       "tech",      hash_pw("tech123"),    "tech",      1),
            (uid(), "Direction",        "direction", hash_pw("dir123"),     "direction", 1),
        ]
        db.executemany("INSERT INTO users VALUES (?,?,?,?,?,?)", default_users)

        default_perms = [
            ("reception", "hotelcheck",    1), ("reception", "maintenance",   1),
            ("reception", "inventory_tech",1), ("reception", "inventory_pdj", 1),
            ("reception", "inventory_fdc", 1),
            ("etage",     "hotelcheck",    1), ("etage",     "maintenance",   1),
            ("etage",     "inventory_tech",0), ("etage",     "inventory_pdj", 0),
            ("etage",     "inventory_fdc", 1),
            ("tech",      "hotelcheck",    1), ("tech",      "maintenance",   1),
            ("tech",      "inventory_tech",1), ("tech",      "inventory_pdj", 0),
            ("tech",      "inventory_fdc", 0),
            ("direction", "hotelcheck",    1), ("direction", "maintenance",   1),
            ("direction", "inventory_tech",1), ("direction", "inventory_pdj", 1),
            ("direction", "inventory_fdc", 1),
            ("admin",     "hotelcheck",    1), ("admin",     "maintenance",   1),
            ("admin",     "inventory_tech",1), ("admin",     "inventory_pdj", 1),
            ("admin",     "inventory_fdc", 1),
        ]
        db.executemany("INSERT INTO permissions VALUES (?,?,?)", default_perms)

        # Default locations
        locs = []
        for n in range(1, 24):
            locs.append((uid(), "Appartement %03d" % n, 1))
        for floor in [1,2,3]:
            for n in range(1, 32):
                locs.append((uid(), "Appartement %d" % (floor*100+n), 1))
        db.executemany("INSERT INTO locations VALUES (?,?,?)", locs)

        # Default tasks
        db.execute("INSERT INTO tasks VALUES (?,?,?,?)", (uid(),"Lave-vaisselle","monthly","all"))
        db.execute("INSERT INTO tasks VALUES (?,?,?,?)", (uid(),"Appliques","monthly","all"))

        # Default staff
        db.execute("INSERT INTO staff VALUES (?,?,?)", (uid(),"Marie","#388bfd"))
        db.execute("INSERT INTO staff VALUES (?,?,?)", (uid(),"Thomas","#3fb950"))

    db.commit()
    db.close()

# ── API helpers ────────────────────────────────────────────────────────────
def rows_to_list(rows):
    return [dict(r) for r in rows]

def row_to_dict(row):
    return dict(row) if row else None

# ── Routes ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if not os.path.exists(HTML_FILE):
        return "hotelhub.html introuvable dans: " + BASE_DIR, 404
    return send_file(HTML_FILE)

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    if not data: return jsonify({"ok": False, "error": "No data"}), 400
    db = get_db()
    user = row_to_dict(db.execute(
        "SELECT * FROM users WHERE username=? AND password=? AND active=1",
        (data.get("username",""), hash_pw(data.get("password","")))
    ).fetchone())
    db.close()
    if not user:
        return jsonify({"ok": False, "error": "Identifiants incorrects"})
    # Get permissions
    db = get_db()
    perms_rows = db.execute("SELECT module, allowed FROM permissions WHERE role=?", (user["role"],)).fetchall()
    db.close()
    perms = {r["module"]: bool(r["allowed"]) for r in perms_rows}
    # Admin always gets all
    if user["role"] == "admin":
        for m in ["hotelcheck","maintenance","inventory_tech","inventory_pdj","inventory_fdc"]:
            perms[m] = True
    return jsonify({"ok": True, "user": {
        "id": user["id"], "name": user["name"],
        "role": user["role"], "username": user["username"]
    }, "permissions": perms})

@app.route("/api/data", methods=["GET"])
def get_data():
    db = get_db()
    locations = rows_to_list(db.execute("SELECT id, name, active FROM locations ORDER BY name").fetchall())
    tasks = rows_to_list(db.execute("SELECT id, name, interval, location_scope FROM tasks").fetchall())
    staff = rows_to_list(db.execute("SELECT id, name, color FROM staff").fetchall())
    checks_raw = rows_to_list(db.execute("SELECT * FROM checks").fetchall())
    history = rows_to_list(db.execute("SELECT * FROM history ORDER BY ts DESC LIMIT 500").fetchall())
    interventions = rows_to_list(db.execute("SELECT * FROM interventions ORDER BY date DESC").fetchall())
    users = rows_to_list(db.execute("SELECT id, name, username, role, active FROM users").fetchall())
    perms_raw = rows_to_list(db.execute("SELECT role, module, allowed FROM permissions").fetchall())
    inv_items = rows_to_list(db.execute("SELECT * FROM inventory_items ORDER BY inv_type, category, name").fetchall())
    inv_moves = rows_to_list(db.execute("SELECT * FROM inventory_movements ORDER BY ts DESC LIMIT 1000").fetchall())
    db.close()

    # Format tasks
    for t in tasks:
        if t["location_scope"] != "all":
            try: t["location_scope"] = json.loads(t["location_scope"])
            except: t["location_scope"] = "all"
        t["locationScope"] = t.pop("location_scope")

    # Format checks as dict
    checks = {}
    for c in checks_raw:
        checks[c["check_key"]] = {
            "date": c["done_date"], "staffId": c["staff_id"],
            "staffName": c["staff_name"], "staffColor": c["staff_color"]
        }

    # Format permissions
    permissions = {}
    for p in perms_raw:
        if p["role"] not in permissions: permissions[p["role"]] = {}
        permissions[p["role"]][p["module"]] = bool(p["allowed"])

    # Format inventory
    inventory = {"tech":{"items":[],"movements":[]},"pdj":{"items":[],"movements":[]},"fdc":{"items":[],"movements":[]}}
    for it in inv_items:
        t = it["inv_type"]
        if t in inventory: inventory[t]["items"].append(it)
    for mv in inv_moves:
        t = mv["inv_type"]
        if t in inventory: inventory[t]["movements"].append(mv)

    # Format interventions
    for iv in interventions:
        iv["locId"] = iv.pop("loc_id", "")
        iv["locName"] = iv.pop("loc_name", "")
        iv["reportedBy"] = iv.pop("reported_by", "")
        iv["assignedTo"] = iv.pop("assigned_to", "")
        iv["resolvedDate"] = iv.pop("resolved_date", "")
        iv["createdAt"] = iv.pop("created_at", 0)

    return jsonify({
        "locations": locations, "tasks": tasks, "staff": staff,
        "checks": checks, "history": history, "interventions": interventions,
        "users": users, "permissions": permissions, "inventory": inventory
    })

@app.route("/api/save", methods=["POST"])
def save_data():
    data = request.json
    if not data: return jsonify({"ok": False, "error": "No data"}), 400
    db = get_db()
    try:
        # ── Locations ──
        if "locations" in data:
            db.execute("DELETE FROM locations")
            for l in data["locations"]:
                db.execute("INSERT INTO locations VALUES (?,?,?)",
                    (l["id"], l["name"], 1 if l.get("active",True) else 0))

        # ── Tasks ──
        if "tasks" in data:
            db.execute("DELETE FROM tasks")
            for t in data["tasks"]:
                scope = t.get("locationScope","all")
                if isinstance(scope, list): scope = json.dumps(scope)
                db.execute("INSERT INTO tasks VALUES (?,?,?,?)",
                    (t["id"], t["name"], t["interval"], scope))

        # ── Staff ──
        if "staff" in data:
            db.execute("DELETE FROM staff")
            for s in data["staff"]:
                db.execute("INSERT INTO staff VALUES (?,?,?)",
                    (s["id"], s["name"], s.get("color","#388bfd")))

        # ── Checks ──
        if "checks" in data:
            db.execute("DELETE FROM checks")
            for k, v in data["checks"].items():
                parts = k.split("__")
                loc_id = parts[0] if len(parts)>0 else ""
                task_id = parts[1] if len(parts)>1 else ""
                period_key = parts[2] if len(parts)>2 else ""
                db.execute("INSERT OR REPLACE INTO checks VALUES (?,?,?,?,?,?,?,?,?)",
                    (k, loc_id, task_id, period_key,
                     v.get("date"), v.get("staffId"), v.get("staffName"), v.get("staffColor"),
                     int(datetime.now().timestamp())))

        # ── History ──
        if "history" in data:
            db.execute("DELETE FROM history")
            for h in data["history"]:
                db.execute("INSERT OR REPLACE INTO history VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (h.get("id") or uid(), h.get("date"), h.get("staffId"), h.get("staffName"),
                     h.get("staffColor"), h.get("locId"), h.get("locName"),
                     h.get("taskId"), h.get("taskName"), h.get("ts",0)))

        # ── Interventions ──
        if "interventions" in data:
            db.execute("DELETE FROM interventions")
            for iv in data["interventions"]:
                db.execute("INSERT INTO interventions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (iv["id"], iv.get("locId",""), iv.get("locName",""), iv.get("date",""),
                     iv.get("description",""), iv.get("reportedBy",""), iv.get("assignedTo",""),
                     iv.get("status","En cours"), iv.get("resolvedDate",""),
                     iv.get("comment",""), iv.get("createdAt",0)))

        # ── Permissions ──
        if "permissions" in data:
            db.execute("DELETE FROM permissions")
            for role, mods in data["permissions"].items():
                for mod, allowed in mods.items():
                    db.execute("INSERT INTO permissions VALUES (?,?,?)",
                        (role, mod, 1 if allowed else 0))

        # ── Users ──
        if "users" in data:
            for u in data["users"]:
                existing = db.execute("SELECT id FROM users WHERE id=?", (u["id"],)).fetchone()
                if existing:
                    db.execute("UPDATE users SET name=?, username=?, role=?, active=? WHERE id=?",
                        (u["name"], u["username"], u["role"], 1 if u.get("active",True) else 0, u["id"]))
                    if u.get("password") and len(u["password"]) != 64:
                        db.execute("UPDATE users SET password=? WHERE id=?",
                            (hash_pw(u["password"]), u["id"]))
                else:
                    pw = u.get("password","")
                    if len(pw) != 64: pw = hash_pw(pw)
                    db.execute("INSERT INTO users VALUES (?,?,?,?,?,?)",
                        (u["id"], u["name"], u["username"], pw, u["role"], 1 if u.get("active",True) else 0))

        # ── Inventory ──
        if "inventory" in data:
            db.execute("DELETE FROM inventory_items")
            db.execute("DELETE FROM inventory_movements")
            for inv_type, inv in data["inventory"].items():
                for it in inv.get("items",[]):
                    db.execute("INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)",
                        (it["id"], inv_type, it["name"], it.get("category",""),
                         it.get("qty",0), it.get("minQty",it.get("min_qty",0)), it.get("unit","unité")))
                for mv in inv.get("movements",[]):
                    db.execute("INSERT INTO inventory_movements VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (mv["id"], inv_type, mv["itemId"] if "itemId" in mv else mv.get("item_id",""),
                         mv.get("itemName",mv.get("item_name","")),
                         mv["type"] if "type" in mv else mv.get("move_type","out"),
                         mv.get("qty",0),
                         mv.get("by",mv.get("by_user","")),
                         mv.get("date",mv.get("move_date","")),
                         mv.get("note",""),
                         mv.get("ts",0)))

        db.commit()
        return jsonify({"ok": True})
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        db.close()

@app.route("/manifest.json")
def manifest():
    return send_file(os.path.join(BASE_DIR, "manifest.json"), mimetype="application/json")

@app.route("/sw.js")
def service_worker():
    return send_file(os.path.join(BASE_DIR, "sw.js"), mimetype="application/javascript")

@app.route("/icon-<size>.png")
def icon(size):
    path = os.path.join(BASE_DIR, "icon-"+size+".png")
    if os.path.exists(path):
        return send_file(path, mimetype="image/png")
    return "", 404

@app.route("/api/info", methods=["GET"])
def info():
    ips = get_all_ips()
    return jsonify({"ip": ips[0] if ips else "127.0.0.1", "ips": ips, "port": PORT, "db": DB_PATH})

# ── Main ───────────────────────────────────────────────────────────────────
def get_all_ips():
    """Return all network IPs (WiFi + Ethernet)"""
    ips = []
    seen = set()
    # Try multiple destinations to discover all interfaces
    for dest in ["8.8.8.8", "192.168.1.1", "192.168.0.1", "10.0.0.1", "172.16.0.1"]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect((dest, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip not in seen and not ip.startswith("127."):
                seen.add(ip)
                ips.append(ip)
        except: pass
    # Also try hostname resolution
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None)
        for info in infos:
            ip = info[4][0]
            if ip not in seen and not ip.startswith("127.") and ":" not in ip:
                seen.add(ip)
                ips.append(ip)
    except: pass
    return ips if ips else ["127.0.0.1"]

def get_local_ip():
    ips = get_all_ips()
    return ips[0] if ips else "127.0.0.1"

def run_server():
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)

def main():
    init_db()
    ip = get_local_ip()
    print("=" * 55)
    print("  HotelHub v2 — Serveur démarré")
    print("  PC local : http://127.0.0.1:%d" % PORT)
    print("  Réseau   : http://%s:%d" % (ip, PORT))
    print("  Base     : %s" % DB_PATH)
    print("  Ctrl+C pour arrêter")
    print("=" * 55)

    # Open browser after short delay
    def open_browser():
        import time; time.sleep(1.0)
        webbrowser.open("http://127.0.0.1:%d" % PORT)
    threading.Thread(target=open_browser, daemon=True).start()

    run_server()

if __name__ == "__main__":
    main()
