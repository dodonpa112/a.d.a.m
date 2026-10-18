from flask import Flask, request, jsonify
import webbrowser
import os

app = Flask(__name__)

@app.route('/execute', methods=['POST'])
def execute_command():
    data = request.json
    action = data.get("action")
    target = data.get("target")
    
    if action == "open_browser":
        if target == "youtube":
            webbrowser.open("https://www.youtube.com")
            return jsonify({"status": "success", "message": "YouTube ouvert sur le PC."})
        elif target == "canvas":
            webbrowser.open("https://ehb.instructure.com")
            return jsonify({"status": "success", "message": "Canvas ouvert sur le PC."})
            
    return jsonify({"status": "error", "message": "Action inconnue."})

if __name__ == '__main__':
    # Lance le serveur en local sur le port 5000
    app.run(port=5000)
