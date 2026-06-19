#!/usr/bin/env python3
"""
HotelHub Server — Flask + PostgreSQL (Supabase)
"""
import os, sys, json, hashlib, uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_file

# ── Paths ──────────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HTML_FILE = os.path.join(BASE_DIR, "hotelhub.html")
PORT      = int(os.environ.get("PORT", 8766))

# ── Flask ──────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── DB Connection ──────────────────────────────────────────────────────────
import pg8000
import pg8000.native
from urllib.parse import urlparse

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def parse_db_url(url):
    p = urlparse(url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "database": p.path.lstrip("/"),
        "user": p.username,
        "password": p.password,
        "ssl_context": True
    }

def get_db():
    params = parse_db_url(DATABASE_URL)
    conn = pg8000.connect(**params)
    return conn

def fetchall_dict(cursor):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]

def fetchone_dict(cursor):
    cols = [d[0] for d in cursor.description]
    row = cursor.fetchone()
    return dict(zip(cols, row)) if row else None

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def new_uid():
    return str(uuid.uuid4())[:8]

# ── DB Init ────────────────────────────────────────────────────────────────
def generate_locations():
    locs = []
    for n in range(1, 24):
        locs.append((new_uid(), "Appartement %03d" % n, True))
    for floor in [1, 2, 3]:
        for n in range(1, 32):
            locs.append((new_uid(), "Appartement %d" % (floor*100+n), True))
    return locs

def init_db():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'reception',
        active BOOLEAN NOT NULL DEFAULT TRUE
    );
    CREATE TABLE IF NOT EXISTS permissions (
        role TEXT NOT NULL,
        module TEXT NOT NULL,
        allowed BOOLEAN NOT NULL DEFAULT TRUE,
        PRIMARY KEY (role, module)
    );
    CREATE TABLE IF NOT EXISTS locations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        active BOOLEAN NOT NULL DEFAULT TRUE
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
        loc_id TEXT,
        task_id TEXT,
        period_key TEXT,
        done_date TEXT,
        staff_id TEXT,
        staff_name TEXT,
        staff_color TEXT,
        done_at BIGINT
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
        ts BIGINT
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
        created_at BIGINT
    );
    CREATE TABLE IF NOT EXISTS inventory_items (
        id TEXT PRIMARY KEY,
        inv_type TEXT NOT NULL,
        name TEXT NOT NULL,
        category TEXT,
        qty REAL DEFAULT 0,
        min_qty REAL DEFAULT 0,
        unit TEXT DEFAULT 'unite'
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
        ts BIGINT
    );
    """)

    # Seed if empty
    cur.execute("SELECT COUNT(*) as c FROM users")
    _cnt = cur.fetchone()
    if (_cnt[0] if isinstance(_cnt,tuple) else _cnt["c"]) == 0:
        users = [
            (new_uid(), "Administrateur", "admin",     hash_pw("admin123"),  "admin",     True),
            (new_uid(), "Reception",      "reception", hash_pw("recep123"),  "reception", True),
            (new_uid(), "Etage",          "etage",     hash_pw("etage123"),  "etage",     True),
            (new_uid(), "Technicien",     "tech",      hash_pw("tech123"),   "tech",      True),
            (new_uid(), "Direction",      "direction", hash_pw("dir123"),    "direction", True),
        ]
        for _u in users: cur.execute("INSERT INTO users VALUES (%s,%s,%s,%s,%s,%s)", _u)

        perms = [
            ("reception","hotelcheck",True),("reception","maintenance",True),
            ("reception","inventory_tech",True),("reception","inventory_pdj",True),("reception","inventory_fdc",True),
            ("etage","hotelcheck",True),("etage","maintenance",True),
            ("etage","inventory_tech",False),("etage","inventory_pdj",False),("etage","inventory_fdc",True),
            ("tech","hotelcheck",True),("tech","maintenance",True),
            ("tech","inventory_tech",True),("tech","inventory_pdj",False),("tech","inventory_fdc",False),
            ("direction","hotelcheck",True),("direction","maintenance",True),
            ("direction","inventory_tech",True),("direction","inventory_pdj",True),("direction","inventory_fdc",True),
            ("admin","hotelcheck",True),("admin","maintenance",True),
            ("admin","inventory_tech",True),("admin","inventory_pdj",True),("admin","inventory_fdc",True),
        ]
        for _p in perms: cur.execute("INSERT INTO permissions VALUES (%s,%s,%s)", _p)

        locs = generate_locations()
        for _l in locs: cur.execute("INSERT INTO locations VALUES (%s,%s,%s)", _l)

        cur.execute("INSERT INTO tasks VALUES (%s,%s,%s,%s)",
            (new_uid(),"Lave-vaisselle","monthly","all"))
        cur.execute("INSERT INTO tasks VALUES (%s,%s,%s,%s)",
            (new_uid(),"Appliques","monthly","all"))
        cur.execute("INSERT INTO staff VALUES (%s,%s,%s)",
            (new_uid(),"Marie","#388bfd"))
        cur.execute("INSERT INTO staff VALUES (%s,%s,%s)",
            (new_uid(),"Thomas","#3fb950"))

    db.commit()
    cur.close()
    db.close()

# ── Routes ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_file(HTML_FILE)

@app.route("/manifest.json")
def manifest():
    return send_file(os.path.join(BASE_DIR,"manifest.json"), mimetype="application/json")

@app.route("/sw.js")
def service_worker():
    return send_file(os.path.join(BASE_DIR,"sw.js"), mimetype="application/javascript")

@app.route("/icon-<size>.png")
def icon(size):
    p = os.path.join(BASE_DIR,"icon-"+size+".png")
    return send_file(p, mimetype="image/png") if os.path.exists(p) else ("",404)

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    if not data: return jsonify({"ok":False,"error":"No data"}),400
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE username=%s AND password=%s AND active=TRUE",
        (data.get("username",""), hash_pw(data.get("password",""))))
    user = fetchone_dict(cur)
    if not user:
        cur.close();db.close()
        return jsonify({"ok":False,"error":"Identifiants incorrects"})
    cur.execute("SELECT module, allowed FROM permissions WHERE role=%s", (user["role"],))
    perms = {r["module"]: bool(r["allowed"]) for r in fetchall_dict(cur)}
    if user["role"] == "admin":
        for m in ["hotelcheck","maintenance","inventory_tech","inventory_pdj","inventory_fdc"]:
            perms[m] = True
    cur.close();db.close()
    return jsonify({"ok":True,"user":{
        "id":user["id"],"name":user["name"],
        "role":user["role"],"username":user["username"]
    },"permissions":perms})

@app.route("/api/data", methods=["GET"])
def get_data():
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT id, name, active FROM locations ORDER BY name")
    locations = fetchall_dict(cur)
    cur.execute("SELECT id, name, interval, location_scope FROM tasks")
    tasks_raw = fetchall_dict(cur)
    cur.execute("SELECT id, name, color FROM staff")
    staff = fetchall_dict(cur)
    cur.execute("SELECT * FROM checks")
    checks_raw = fetchall_dict(cur)
    cur.execute("SELECT * FROM history ORDER BY ts DESC LIMIT 500")
    history = fetchall_dict(cur)
    cur.execute("SELECT * FROM interventions ORDER BY date DESC")
    interventions_raw = fetchall_dict(cur)
    cur.execute("SELECT id, name, username, role, active FROM users")
    users = fetchall_dict(cur)
    cur.execute("SELECT role, module, allowed FROM permissions")
    perms_raw = fetchall_dict(cur)
    cur.execute("SELECT * FROM inventory_items ORDER BY inv_type, category, name")
    inv_items = fetchall_dict(cur)
    cur.execute("SELECT * FROM inventory_movements ORDER BY ts DESC LIMIT 1000")
    inv_moves = fetchall_dict(cur)
    cur.close();db.close()

    # Format tasks
    tasks = []
    for t in tasks_raw:
        td = dict(t)
        scope = td.pop("location_scope","all")
        if scope != "all":
            try: scope = json.loads(scope)
            except: scope = "all"
        td["locationScope"] = scope
        tasks.append(td)

    # Format checks
    checks = {}
    for c in checks_raw:
        checks[c["check_key"]] = {
            "date":c["done_date"],"staffId":c["staff_id"],
            "staffName":c["staff_name"],"staffColor":c["staff_color"]
        }

    # Format permissions
    permissions = {}
    for p in perms_raw:
        if p["role"] not in permissions: permissions[p["role"]] = {}
        permissions[p["role"]][p["module"]] = bool(p["allowed"])

    # Format inventory
    inventory = {
        "tech":{"items":[],"movements":[]},
        "pdj": {"items":[],"movements":[]},
        "fdc": {"items":[],"movements":[]}
    }
    for it in inv_items:
        t2 = it["inv_type"]
        if t2 in inventory:
            item = dict(it)
            item["minQty"] = item.get("min_qty", 0)
            inventory[t2]["items"].append(item)
    for mv in inv_moves:
        t2 = mv["inv_type"]
        if t2 in inventory:
            m2 = dict(mv)
            m2["itemId"]   = m2.pop("item_id","")
            m2["itemName"] = m2.pop("item_name","")
            m2["type"]     = m2.pop("move_type","out")
            m2["by"]       = m2.pop("by_user","")
            m2["date"]     = m2.pop("move_date","")
            inventory[t2]["movements"].append(m2)

    # Format interventions
    interventions = []
    for iv in interventions_raw:
        d2 = dict(iv)
        d2["locId"]       = d2.pop("loc_id","")
        d2["locName"]     = d2.pop("loc_name","")
        d2["reportedBy"]  = d2.pop("reported_by","")
        d2["assignedTo"]  = d2.pop("assigned_to","")
        d2["resolvedDate"]= d2.pop("resolved_date","")
        d2["createdAt"]   = d2.pop("created_at",0)
        interventions.append(d2)

    return jsonify({
        "locations":locations,"tasks":tasks,"staff":staff,
        "checks":checks,"history":history,"interventions":interventions,
        "users":users,"permissions":permissions,"inventory":inventory
    })

@app.route("/api/save", methods=["POST"])
def save_data():
    data = request.json
    if not data: return jsonify({"ok":False,"error":"No data"}),400
    db = get_db(); cur = db.cursor()
    try:
        # Locations
        if "locations" in data:
            cur.execute("DELETE FROM locations")
            for l in data["locations"]:
                cur.execute("INSERT INTO locations VALUES (%s,%s,%s)",
                    (l["id"],l["name"],bool(l.get("active",True))))

        # Tasks
        if "tasks" in data:
            cur.execute("DELETE FROM tasks")
            for t in data["tasks"]:
                scope = t.get("locationScope","all")
                if isinstance(scope,list): scope = json.dumps(scope)
                cur.execute("INSERT INTO tasks VALUES (%s,%s,%s,%s)",
                    (t["id"],t["name"],t["interval"],scope))

        # Staff
        if "staff" in data:
            cur.execute("DELETE FROM staff")
            for s in data["staff"]:
                cur.execute("INSERT INTO staff VALUES (%s,%s,%s)",
                    (s["id"],s["name"],s.get("color","#388bfd")))

        # Checks
        if "checks" in data:
            cur.execute("DELETE FROM checks")
            for k,v in data["checks"].items():
                parts = k.split("__")
                cur.execute("INSERT INTO checks VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (k, parts[0] if len(parts)>0 else "",
                     parts[1] if len(parts)>1 else "",
                     parts[2] if len(parts)>2 else "",
                     v.get("date"),v.get("staffId"),v.get("staffName"),v.get("staffColor"),
                     int(datetime.now().timestamp())))

        # History
        if "history" in data:
            cur.execute("DELETE FROM history")
            for h in data["history"]:
                cur.execute("INSERT INTO history VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (h.get("id") or new_uid(),h.get("date"),h.get("staffId"),h.get("staffName"),
                     h.get("staffColor"),h.get("locId"),h.get("locName"),
                     h.get("taskId"),h.get("taskName"),h.get("ts",0)))

        # Interventions
        if "interventions" in data:
            cur.execute("DELETE FROM interventions")
            for iv in data["interventions"]:
                cur.execute("INSERT INTO interventions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (iv["id"],iv.get("locId",""),iv.get("locName",""),iv.get("date",""),
                     iv.get("description",""),iv.get("reportedBy",""),iv.get("assignedTo",""),
                     iv.get("status","En cours"),iv.get("resolvedDate",""),
                     iv.get("comment",""),iv.get("createdAt",0)))

        # Permissions
        if "permissions" in data:
            cur.execute("DELETE FROM permissions")
            for role,mods in data["permissions"].items():
                for mod,allowed in mods.items():
                    cur.execute("INSERT INTO permissions VALUES (%s,%s,%s)",
                        (role,mod,bool(allowed)))

        # Users
        if "users" in data:
            for u in data["users"]:
                cur.execute("SELECT id FROM users WHERE id=%s",(u["id"],))
                if cur.fetchone():
                    cur.execute("UPDATE users SET name=%s,username=%s,role=%s,active=%s WHERE id=%s",
                        (u["name"],u["username"],u["role"],bool(u.get("active",True)),u["id"]))
                    pw = u.get("password","")
                    if pw and len(pw) != 64:
                        cur.execute("UPDATE users SET password=%s WHERE id=%s",
                            (hash_pw(pw),u["id"]))
                else:
                    pw = u.get("password","")
                    if len(pw) != 64: pw = hash_pw(pw)
                    cur.execute("INSERT INTO users VALUES (%s,%s,%s,%s,%s,%s)",
                        (u["id"],u["name"],u["username"],pw,u["role"],bool(u.get("active",True))))

        # Inventory
        if "inventory" in data:
            cur.execute("DELETE FROM inventory_items")
            cur.execute("DELETE FROM inventory_movements")
            for inv_type,inv in data["inventory"].items():
                for it in inv.get("items",[]):
                    cur.execute("INSERT INTO inventory_items VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (it["id"],inv_type,it["name"],it.get("category",""),
                         it.get("qty",0),it.get("minQty",it.get("min_qty",0)),it.get("unit","unite")))
                for mv in inv.get("movements",[]):
                    cur.execute("INSERT INTO inventory_movements VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (mv["id"],inv_type,
                         mv.get("itemId",mv.get("item_id","")),
                         mv.get("itemName",mv.get("item_name","")),
                         mv.get("type",mv.get("move_type","out")),
                         mv.get("qty",0),
                         mv.get("by",mv.get("by_user","")),
                         mv.get("date",mv.get("move_date","")),
                         mv.get("note",""),mv.get("ts",0)))

        db.commit()
        return jsonify({"ok":True})
    except Exception as e:
        db.rollback()
        return jsonify({"ok":False,"error":str(e)}),500
    finally:
        cur.close();db.close()

@app.route("/api/info")
def info():
    import socket
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(("8.8.8.8",80))
        ip=s.getsockname()[0];s.close()
    except: ip="127.0.0.1"
    return jsonify({"ip":ip,"port":PORT})

# ── Main ───────────────────────────────────────────────────────────────────
def run_server():
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)

def main():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set!")
        print("Set it in Railway Variables or .env file")
        return
    init_db()
    print("HotelHub started on port", PORT)
    run_server()

if __name__ == "__main__":
    main()
