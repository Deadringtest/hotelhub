╔══════════════════════════════════════════════════════════╗
║           HOTELHUB — Guide d'installation                ║
╚══════════════════════════════════════════════════════════╝

FICHIERS REQUIS (tous dans le même dossier) :
  • launcher.py          ← Point d'entrée, lancez ce fichier
  • server.py            ← Serveur Flask + SQLite
  • hotelhub.html        ← Interface web
  • hotelhub_config.json ← Configuration (créé automatiquement)
  • hotelhub.db          ← Base de données (créée automatiquement)

══════════════════════════════════════════════════════════

INSTALLATION (une seule fois)
─────────────────────────────
1. Installez Python : https://python.org  (version 3.8+)
   ✓ Cochez "Add Python to PATH" lors de l'installation

2. Ouvrez un terminal dans ce dossier (clic droit → Terminal)
   puis tapez :
     pip install flask pystray pillow

3. Lancez l'app :
     python launcher.py

══════════════════════════════════════════════════════════

UTILISATION
────────────
• Le navigateur s'ouvre automatiquement sur ce PC
• Icône 🏨 dans la barre des tâches → menu avec toutes les IPs
• Autres PC/téléphones : tapez l'IP affichée dans le systray

COMPTES PAR DÉFAUT :
  admin     / admin123   (tout + gestion utilisateurs)
  reception / recep123
  etage     / etage123
  tech      / tech123
  direction / dir123

══════════════════════════════════════════════════════════

DÉMARRAGE AUTOMATIQUE AVEC WINDOWS
────────────────────────────────────
Clic droit sur l'icône 🏨 → "Démarrer avec Windows ✓"
L'app se lancera automatiquement à chaque démarrage du PC.

══════════════════════════════════════════════════════════

IP FIXE (recommandé)
──────────────────────
Clic droit sur l'icône 🏨 → "IP fixe" → choisissez l'IP
de votre réseau hôtel. Elle sera mémorisée.

══════════════════════════════════════════════════════════

ANTIVIRUS
──────────
Si votre antivirus bloque l'app :
  Windows Defender → Sécurité Windows → Protection virus
  → Gérer les paramètres → Exclusions → Ajouter un dossier
  → Sélectionnez le dossier HotelHub

══════════════════════════════════════════════════════════

SAUVEGARDE
───────────
Copiez régulièrement le fichier hotelhub.db
C'est votre base de données complète.
