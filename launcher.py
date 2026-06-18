#!/usr/bin/env python3
"""
HotelHub Launcher — Systray + Flask server
"""
import sys, os, threading, webbrowser, socket, time, json

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "hotelhub_config.json")

# Hide console on Windows
if sys.platform == "win32":
    import ctypes
    ctypes.windll.user32.ShowWindow(
        ctypes.windll.kernel32.GetConsoleWindow(), 0)

PORT = 8766

# ── Config (static IP option) ──────────────────────────────────────────────
def load_config():
    default = {"static_ip": None, "port": 8766, "autostart": False}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                d = json.load(f)
            default.update(d)
        except: pass
    return default

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# ── IP detection ───────────────────────────────────────────────────────────
def get_all_ips():
    ips = []
    seen = set()
    for dest in ["8.8.8.8", "192.168.1.1", "192.168.0.1", "10.0.0.1"]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect((dest, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip not in seen and not ip.startswith("127."):
                seen.add(ip); ips.append(ip)
        except: pass
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None)
        for info in infos:
            ip = info[4][0]
            if ip not in seen and not ip.startswith("127.") and ":" not in ip:
                seen.add(ip); ips.append(ip)
    except: pass
    return ips if ips else ["127.0.0.1"]

def get_display_ip(cfg):
    if cfg.get("static_ip"):
        return cfg["static_ip"]
    ips = get_all_ips()
    return ips[0] if ips else "127.0.0.1"

# ── Autostart ──────────────────────────────────────────────────────────────
def setup_autostart(enable):
    if sys.platform != "win32": return
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
            winreg.KEY_SET_VALUE)
        if enable:
            exe = sys.executable if getattr(sys,'frozen',False) else os.path.abspath(__file__)
            winreg.SetValueEx(key, "HotelHub", 0, winreg.REG_SZ, '"'+exe+'"')
        else:
            try: winreg.DeleteValue(key, "HotelHub")
            except: pass
        winreg.CloseKey(key)
    except: pass

def is_autostart():
    if sys.platform != "win32": return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, "HotelHub")
        winreg.CloseKey(key)
        return True
    except: return False

# ── Systray icon ───────────────────────────────────────────────────────────
def create_icon_image():
    try:
        from PIL import Image, ImageDraw
        img = Image.new('RGBA', (64, 64), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2,2,62,62], fill=(31,56,100,255))
        draw.rectangle([16,20,24,44], fill=(255,255,255,255))
        draw.rectangle([40,20,48,44], fill=(255,255,255,255))
        draw.rectangle([16,30,48,34], fill=(255,255,255,255))
        return img
    except:
        try:
            from PIL import Image
            return Image.new('RGB', (64,64), (31,56,100))
        except: return None

def run_systray(cfg):
    try:
        import pystray
        from pystray import MenuItem as item

        ips = get_all_ips()
        static_ip = cfg.get("static_ip")

        def open_local(icon=None, it=None):
            webbrowser.open("http://127.0.0.1:%d" % PORT)

        def open_network(ip):
            def _open(icon=None, it=None):
                webbrowser.open("http://%s:%d" % (ip, PORT))
            return _open

        def toggle_autostart(icon, it):
            new_val = not is_autostart()
            setup_autostart(new_val)
            cfg["autostart"] = new_val
            save_config(cfg)
            rebuild_menu(icon)

        def set_static_ip(ip):
            def _set(icon, it):
                cfg["static_ip"] = ip
                save_config(cfg)
                rebuild_menu(icon)
                show_notification(icon, "IP fixe définie", "Accès réseau : http://%s:%d" % (ip, PORT))
            return _set

        def clear_static_ip(icon, it):
            cfg["static_ip"] = None
            save_config(cfg)
            rebuild_menu(icon)

        def show_notification(icon, title, msg):
            try: icon.notify(msg, title)
            except: pass

        def quit_app(icon, it):
            icon.stop()
            os._exit(0)

        def rebuild_menu(icon):
            icon.menu = build_menu()

        def build_menu():
            ips = get_all_ips()
            auto = is_autostart()
            static = cfg.get("static_ip")

            network_items = []
            # Local access
            network_items.append(item(
                "Ouvrir sur ce PC",
                open_local
            ))
            # All network IPs
            if len(ips) == 0:
                network_items.append(item("Aucune interface réseau détectée", lambda i,it: None, enabled=False))
            else:
                for ip in ips:
                    label = "http://%s:%d" % (ip, PORT)
                    if static == ip:
                        label += "  ★ (IP fixe)"
                    network_items.append(item(label, open_network(ip)))

            # Static IP submenu
            static_items = [item("Désactiver l'IP fixe", clear_static_ip)]
            for ip in ips:
                mark = "  ★" if static == ip else ""
                static_items.append(item("Fixer sur %s%s" % (ip, mark), set_static_ip(ip)))

            same_network = len(set(ip.rsplit(".",1)[0] for ip in ips)) == 1 if len(ips)>1 else True
            network_warning = [] if same_network or len(ips)<=1 else [
                item("⚠ Réseaux différents détectés", lambda i,it: None, enabled=False),
                item("Choisissez l'IP ci-dessus selon", lambda i,it: None, enabled=False),
                item("le réseau de vos appareils", lambda i,it: None, enabled=False),
            ]

            return pystray.Menu(
                item("🏨  HotelHub", lambda i,it: None, enabled=False),
                item("Serveur actif — Port %d" % PORT, lambda i,it: None, enabled=False),
                pystray.Menu.SEPARATOR,
                *network_items,
                pystray.Menu.SEPARATOR,
                *network_warning,
                item("IP fixe (ne change pas)", pystray.Menu(*static_items)),
                pystray.Menu.SEPARATOR,
                item("Démarrer avec Windows  %s" % ("✓" if auto else ""), toggle_autostart),
                pystray.Menu.SEPARATOR,
                item("Quitter HotelHub", quit_app),
            )

        img = create_icon_image()
        if not img: raise Exception("No icon")

        icon = pystray.Icon("HotelHub", img, "HotelHub ● Actif", build_menu())

        # Show startup notification after 2s
        def notify_start():
            time.sleep(2)
            ips = get_all_ips()
            static = cfg.get("static_ip")
            display_ip = static if static else (ips[0] if ips else "127.0.0.1")
            try:
                icon.notify(
                    "Accès réseau : http://%s:%d\nPC local : http://127.0.0.1:%d" % (display_ip, PORT, PORT),
                    "HotelHub démarré"
                )
            except: pass
        threading.Thread(target=notify_start, daemon=True).start()

        icon.run()

    except Exception as e:
        print("Systray non disponible:", e)
        ips = get_all_ips()
        print("HotelHub actif :")
        print("  Local  : http://127.0.0.1:%d" % PORT)
        for ip in ips:
            print("  Réseau : http://%s:%d" % (ip, PORT))
        print("Ctrl+C pour arrêter")
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            os._exit(0)

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    cfg = load_config()
    global PORT
    PORT = cfg.get("port", 8766)

    # Start Flask server
    sys.path.insert(0, BASE_DIR)
    try:
        import server as hotelhub_server
        hotelhub_server.BASE_DIR  = BASE_DIR
        hotelhub_server.DB_PATH   = os.path.join(BASE_DIR, "hotelhub.db")
        hotelhub_server.HTML_FILE = os.path.join(BASE_DIR, "hotelhub.html")
        hotelhub_server.PORT      = PORT
        hotelhub_server.init_db()

        flask_thread = threading.Thread(target=hotelhub_server.run_server, daemon=True)
        flask_thread.start()
        time.sleep(1.0)
    except Exception as e:
        print("Erreur démarrage serveur:", e)
        input("Appuyez sur Entree pour quitter...")
        return

    # Open browser on this PC
    webbrowser.open("http://127.0.0.1:%d" % PORT)

    # Sync autostart config
    if is_autostart() != cfg.get("autostart", False):
        cfg["autostart"] = is_autostart()
        save_config(cfg)

    # Run systray (blocking)
    run_systray(cfg)

if __name__ == "__main__":
    main()
