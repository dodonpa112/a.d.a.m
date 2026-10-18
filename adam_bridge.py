import os
import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

# Traduction automatique des noms courants en exécutables Windows officiels
APP_ALIASES = {
    "bloc-notes": "notepad",
    "bloc notes": "notepad",
    "bloc note": "notepad",
    "notepad": "notepad",
    "calculatrice": "calc",
    "calc": "calc",
    "chrome": "chrome",
    "google chrome": "chrome",
    "navigateur": "chrome",
    "edge": "msedge",
    "explorateur": "explorer",
    "fichiers": "explorer",
    "terminal": "cmd",
    "invite de commandes": "cmd",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "spotify": "spotify",
    "discord": "discord",
    "vscode": "code",
    "vs code": "code",
    "parametres": "ms-settings:",
    "paramètres": "ms-settings:"
}

@app.route('/execute', methods=['POST'])
def execute_command():
    data = request.get_json(silent=True) or {}
    print(f"\n[A.D.A.M. BRIDGE] Requête reçue : {data}")
    
    # Accepte app_name, target ou action (compatibilité totale)
    raw_target = data.get('app_name') or data.get('target') or data.get('action') or ''
    clean_target = str(raw_target).strip().lower()

    if not clean_target:
        print("[ERREUR] Aucune application spécifiée dans la requête.")
        return jsonify({"status": "error", "message": "Aucune application spécifiée."}), 400

    # Vérifie si le mot correspond à un alias connu, sinon garde le nom envoyé
    executable = APP_ALIASES.get(clean_target, clean_target)
    print(f"[ACTION] Lancement sur Windows de : '{executable}'")

    try:
        # 1. Méthode native Windows la plus directe (équivalent du double-clic / Win+R)
        os.startfile(executable)
        print("[SUCCÈS] Application ouverte via os.startfile.")
        return jsonify({"status": "success", "message": f"Application '{executable}' ouverte."}), 200
    except Exception:
        try:
            # 2. Fallback via l'invite de commande si os.startfile ne trouve pas le chemin direct
            subprocess.Popen(f'start "" "{executable}"', shell=True)
            print("[SUCCÈS] Application ouverte via subprocess start.")
            return jsonify({"status": "success", "message": f"Commande start '{executable}' exécutée."}), 200
        except Exception as e:
            print(f"[ERREUR CRITIQUE] {str(e)}")
            return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    print("🛡️ Pont local A.D.A.M. actif sur http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
