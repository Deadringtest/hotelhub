#!/usr/bin/env python3
"""
HotelHub Server — Flask + Supabase REST API
Utilise l'API HTTP Supabase (port 443) - compatible Railway gratuit
"""
import os, sys, json, hashlib, uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_file

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HTML_FILE = os.path.join(BASE_DIR, "hotelhub.html")
PORT      = int(os.environ.get("PORT", 8766))

SUPABASE_URL    = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY", "")

app = Flask(__name__)

# ── Supabase REST helpers ──────────────────────────────────────────────────
import urllib.request
import urllib.error

def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def sb_get(table, params=""):
    url = SUPABASE_URL + "/rest/v1/" + table + ("?" + params if params else "")
    req = urllib.request.Request(url, headers=sb_headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise Exception("GET %s failed: %s %s" % (table, e.code, e.read().decode()))

def sb_post(table, data):
    url = SUPABASE_URL + "/rest/v1/" + table
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=sb_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = r.read().decode()
            return json.loads(result) if result.strip() else []
    except urllib.error.HTTPError as e:
        raise Exception("POST %s failed: %s %s" % (table, e.code, e.read().decode()))

def sb_delete(table, params=""):
    url = SUPABASE_URL + "/rest/v1/" + table + ("?" + params if params else "")
    req = urllib.request.Request(url, headers=sb_headers(), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        raise Exception("DELETE %s failed: %s %s" % (table, e.code, e.read().decode()))

def sb_patch(table, params, data):
    url = SUPABASE_URL + "/rest/v1/" + table + ("?" + params if params else "")
    body = json.dumps(data).encode()
    headers = dict(sb_headers())
    req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = r.read().decode()
            return json.loads(result) if result.strip() else []
    except urllib.error.HTTPError as e:
        raise Exception("PATCH %s failed: %s %s" % (table, e.code, e.read().decode()))

def sb_upsert(table, data):
    url = SUPABASE_URL + "/rest/v1/" + table
    body = json.dumps(data).encode()
    headers = dict(sb_headers())
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            result = r.read().decode()
            return json.loads(result) if result.strip() else []
    except urllib.error.HTTPError as e:
        raise Exception("UPSERT %s failed: %s %s" % (table, e.code, e.read().decode()))

# ── Helpers ────────────────────────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def new_uid():
    return str(uuid.uuid4())[:8]

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

# ── Routes ─────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_file(HTML_FILE)

@app.route("/manifest.json")
def manifest():
    p = os.path.join(BASE_DIR, "manifest.json")
    return send_file(p, mimetype="application/json") if os.path.exists(p) else ("", 404)

@app.route("/sw.js")
def service_worker():
    p = os.path.join(BASE_DIR, "sw.js")
    return send_file(p, mimetype="application/javascript") if os.path.exists(p) else ("", 404)

@app.route("/icon-<size>.png")
def icon(size):
    p = os.path.join(BASE_DIR, "icon-" + size + ".png")
    return send_file(p, mimetype="image/png") if os.path.exists(p) else ("", 404)

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    if not data:
        return jsonify({"ok": False, "error": "No data"}), 400
    username = data.get("username", "")
    password = hash_pw(data.get("password", ""))
    try:
        users = sb_get("users", "username=eq.%s&password=eq.%s&active=eq.true" % (username, password))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    if not users:
        return jsonify({"ok": False, "error": "Identifiants incorrects"})
    user = users[0]
    try:
        perms_raw = sb_get("permissions", "role=eq." + user["role"])
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    perms = {p["module"]: bool(p["allowed"]) for p in perms_raw}
    if user["role"] == "admin":
        for m in ["hotelcheck","maintenance","inventory_tech","inventory_pdj","inventory_fdc"]:
            perms[m] = True
    return jsonify({"ok": True, "user": {
        "id": user["id"], "name": user["name"],
        "role": user["role"], "username": user["username"]
    }, "permissions": perms})

@app.route("/api/data", methods=["GET"])
def get_data():
    try:
        locations     = sb_get("locations",     "order=name")
        tasks_raw     = sb_get("tasks",         "")
        staff         = sb_get("staff",         "")
        checks_raw    = sb_get("checks",        "")
        history       = sb_get("history",       "order=ts.desc&limit=500")
        ivs_raw       = sb_get("interventions", "order=date.desc")
        users         = sb_get("users",         "select=id,name,username,role,active")
        perms_raw     = sb_get("permissions",   "")
        inv_items     = sb_get("inventory_items","order=inv_type,category,name")
        inv_moves     = sb_get("inventory_movements","order=ts.desc&limit=1000")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Format tasks
    tasks = []
    for t in tasks_raw:
        scope = t.get("location_scope", "all")
        if scope and scope != "all":
            try: scope = json.loads(scope)
            except: scope = "all"
        tasks.append({
            "id": t["id"], "name": t["name"],
            "interval": t["interval"], "locationScope": scope
        })

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
        if p["role"] not in permissions:
            permissions[p["role"]] = {}
        permissions[p["role"]][p["module"]] = bool(p["allowed"])

    # Format inventory
    inventory = {
        "tech": {"items": [], "movements": []},
        "pdj":  {"items": [], "movements": []},
        "fdc":  {"items": [], "movements": []}
    }
    for it in inv_items:
        t2 = it.get("inv_type", "")
        if t2 in inventory:
            item = dict(it)
            item["minQty"] = item.get("min_qty", 0)
            inventory[t2]["items"].append(item)
    for mv in inv_moves:
        t2 = mv.get("inv_type", "")
        if t2 in inventory:
            inventory[t2]["movements"].append({
                "id":       mv["id"],
                "itemId":   mv.get("item_id", ""),
                "itemName": mv.get("item_name", ""),
                "type":     mv.get("move_type", "out"),
                "qty":      mv.get("qty", 0),
                "by":       mv.get("by_user", ""),
                "date":     mv.get("move_date", ""),
                "note":     mv.get("note", ""),
                "ts":       mv.get("ts", 0)
            })

    # Format interventions
    interventions = []
    for iv in ivs_raw:
        interventions.append({
            "id":           iv["id"],
            "locId":        iv.get("loc_id", ""),
            "locName":      iv.get("loc_name", ""),
            "date":         iv.get("date", ""),
            "description":  iv.get("description", ""),
            "reportedBy":   iv.get("reported_by", ""),
            "assignedTo":   iv.get("assigned_to", ""),
            "status":       iv.get("status", "En cours"),
            "resolvedDate": iv.get("resolved_date", ""),
            "comment":      iv.get("comment", ""),
            "createdAt":    iv.get("created_at", 0)
        })

    return jsonify({
        "locations": locations, "tasks": tasks, "staff": staff,
        "checks": checks, "history": history,
        "interventions": interventions, "users": users,
        "permissions": permissions, "inventory": inventory
    })

@app.route("/api/save", methods=["POST"])
def save_data():
    data = request.json
    if not data:
        return jsonify({"ok": False, "error": "No data"}), 400
    try:
        # Locations
        if "locations" in data:
            sb_delete("locations", "id=neq.__none__")
            for chunk in chunks(data["locations"], 50):
                sb_upsert("locations", [{"id":l["id"],"name":l["name"],"active":bool(l.get("active",True))} for l in chunk])

        # Tasks
        if "tasks" in data:
            sb_delete("tasks", "id=neq.__none__")
            if data["tasks"]:
                rows = []
                for t in data["tasks"]:
                    scope = t.get("locationScope","all")
                    if isinstance(scope, list): scope = json.dumps(scope)
                    rows.append({"id":t["id"],"name":t["name"],"interval":t["interval"],"location_scope":scope})
                sb_upsert("tasks", rows)

        # Staff
        if "staff" in data:
            sb_delete("staff", "id=neq.__none__")
            if data["staff"]:
                sb_upsert("staff", [{"id":s["id"],"name":s["name"],"color":s.get("color","#388bfd")} for s in data["staff"]])

        # Checks
        if "checks" in data:
            sb_delete("checks", "check_key=neq.__none__")
            if data["checks"]:
                rows = []
                ts = int(datetime.now().timestamp())
                for k,v in data["checks"].items():
                    parts = k.split("__")
                    rows.append({
                        "check_key": k,
                        "loc_id":    parts[0] if len(parts)>0 else "",
                        "task_id":   parts[1] if len(parts)>1 else "",
                        "period_key":parts[2] if len(parts)>2 else "",
                        "done_date": v.get("date"),
                        "staff_id":  v.get("staffId"),
                        "staff_name":v.get("staffName"),
                        "staff_color":v.get("staffColor"),
                        "done_at":   ts
                    })
                for chunk in chunks(rows, 50):
                    sb_upsert("checks", chunk)

        # History
        if "history" in data:
            sb_delete("history", "id=neq.__none__")
            if data["history"]:
                rows = [{"id":h.get("id") or new_uid(),"done_date":h.get("date"),"staff_id":h.get("staffId"),"staff_name":h.get("staffName"),"staff_color":h.get("staffColor"),"loc_id":h.get("locId"),"loc_name":h.get("locName"),"task_id":h.get("taskId"),"task_name":h.get("taskName"),"ts":h.get("ts",0)} for h in data["history"]]
                for chunk in chunks(rows, 50):
                    sb_upsert("history", chunk)

        # Interventions
        if "interventions" in data:
            sb_delete("interventions", "id=neq.__none__")
            if data["interventions"]:
                rows = [{"id":iv["id"],"loc_id":iv.get("locId",""),"loc_name":iv.get("locName",""),"date":iv.get("date",""),"description":iv.get("description",""),"reported_by":iv.get("reportedBy",""),"assigned_to":iv.get("assignedTo",""),"status":iv.get("status","En cours"),"resolved_date":iv.get("resolvedDate",""),"comment":iv.get("comment",""),"created_at":iv.get("createdAt",0)} for iv in data["interventions"]]
                for chunk in chunks(rows, 50):
                    sb_upsert("interventions", chunk)

        # Permissions
        if "permissions" in data:
            sb_delete("permissions", "role=neq.__none__")
            rows = []
            for role, mods in data["permissions"].items():
                for mod, allowed in mods.items():
                    rows.append({"role":role,"module":mod,"allowed":bool(allowed)})
            if rows:
                sb_upsert("permissions", rows)

        # Users
        if "users" in data:
            for u in data["users"]:
                existing = sb_get("users", "id=eq." + u["id"])
                pw = u.get("password","")
                if existing:
                    update = {"name":u["name"],"username":u["username"],"role":u["role"],"active":bool(u.get("active",True))}
                    if pw and len(pw) != 64:
                        update["password"] = hash_pw(pw)
                    sb_patch("users", "id=eq."+u["id"], update)
                else:
                    if len(pw) != 64: pw = hash_pw(pw)
                    sb_upsert("users", [{"id":u["id"],"name":u["name"],"username":u["username"],"password":pw,"role":u["role"],"active":bool(u.get("active",True))}])

        # Inventory
        if "inventory" in data:
            sb_delete("inventory_items",     "id=neq.__none__")
            sb_delete("inventory_movements", "id=neq.__none__")
            for inv_type, inv in data["inventory"].items():
                if inv.get("items"):
                    rows = [{"id":it["id"],"inv_type":inv_type,"name":it["name"],"category":it.get("category",""),"qty":it.get("qty",0),"min_qty":it.get("minQty",it.get("min_qty",0)),"unit":it.get("unit","unite")} for it in inv["items"]]
                    for chunk in chunks(rows, 50):
                        sb_upsert("inventory_items", chunk)
                if inv.get("movements"):
                    rows = [{"id":mv["id"],"inv_type":inv_type,"item_id":mv.get("itemId",mv.get("item_id","")),"item_name":mv.get("itemName",mv.get("item_name","")),"move_type":mv.get("type",mv.get("move_type","out")),"qty":mv.get("qty",0),"by_user":mv.get("by",mv.get("by_user","")),"move_date":mv.get("date",mv.get("move_date","")),"note":mv.get("note",""),"ts":mv.get("ts",0)} for mv in inv["movements"]]
                    for chunk in chunks(rows, 50):
                        sb_upsert("inventory_movements", chunk)

        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/info")
def info():
    import socket
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(("8.8.8.8",80))
        ip=s.getsockname()[0];s.close()
    except: ip="127.0.0.1"
    return jsonify({"ip":ip,"port":PORT,"supabase":bool(SUPABASE_URL)})

def run_server():
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set!")
        return
    print("HotelHub started on port", PORT)
    print("Supabase:", SUPABASE_URL)
    run_server()

if __name__ == "__main__":
    main()
