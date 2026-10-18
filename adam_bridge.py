import subprocess
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/execute', methods=['POST'])
def execute_command():
    data = request.json
    
    # Récupère le nom de l'application envoyé par l'IA
    target_app = data.get('app_name', '').strip() 

    if not target_app:
        return jsonify({"status": "error", "message": "Aucune application spécifiée."})

    try:
        # Demande à Windows de lancer le programme dynamiquement
        subprocess.Popen(['cmd', '/c', 'start', target_app], shell=True)
        return jsonify({"status": "success", "message": f"Ordre de lancement pour {target_app} exécuté."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erreur système : {str(e)}"})

if __name__ == '__main__':
    app.run(port=5000)
