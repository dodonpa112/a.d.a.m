import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/execute', methods=['POST'])
def execute_command():
    data = request.json
    print(f"\n[DEBUG] Requête reçue de l'IA : {data}") # Affiche les données brutes
    
    target_app = data.get('app_name', '').strip() 
    print(f"[DEBUG] Application extraite : '{target_app}'") # Affiche ce qu'il va lancer

    if not target_app:
        print("[ERREUR] Le nom de l'application est vide.")
        return jsonify({"status": "error", "message": "Aucune application spécifiée."})

    try:
        print(f"[ACTION] Tentative d'ouverture de : {target_app}...")
        subprocess.Popen(['cmd', '/c', 'start', target_app], shell=True)
        print("[SUCCÈS] Ordre envoyé à Windows.")
        return jsonify({"status": "success", "message": f"Ordre de lancement pour '{target_app}' exécuté."})
    except Exception as e:
        print(f"[ERREUR CRITIQUE] {str(e)}")
        return jsonify({"status": "error", "message": f"Erreur système : {str(e)}"})

if __name__ == '__main__':
    app.run(port=5000)
