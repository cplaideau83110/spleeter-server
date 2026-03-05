import os
import requests
import spleeter
from flask import Flask, request, jsonify
from flask_cors import CORS
from spleeter.separator import Separator
from pathlib import Path
import json
import threading

app = Flask(__name__)
CORS(app)

# Variables d'environnement
BASE44_APP_ID = os.environ.get("BASE44_APP_ID", "69a8f857a6a0fa216be33357")
BASE44_SERVICE_KEY = os.environ.get("BASE44_SERVICE_KEY", "")
BASE44_API_URL = "https://api.base44.com/api/apps"

# Store pour le progress (en mémoire)
progress_store = {}

def update_separation(separation_id, data):
    """Met à jour la séparation dans Base44 via Service Role"""
    url = f"{BASE44_API_URL}/{BASE44_APP_ID}/entities/Separation/{separation_id}"
    headers = {
        "Authorization": f"Bearer {BASE44_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.patch(url, json=data, headers=headers)
        response.raise_for_status()
        print(f"✓ Séparation {separation_id} mise à jour")
    except Exception as e:
        print(f"✗ Erreur update: {e}")

def download_file(url):
    """Télécharge un fichier et retourne le chemin local"""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    local_path = f"/tmp/{Path(url).name}"
    with open(local_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    return local_path

def upload_to_base44(local_file_path, filename):
    """Upload un fichier vers Base44 et retourne l'URL publique"""
    url = f"{BASE44_API_URL}/{BASE44_APP_ID}/files/upload"
    headers = {"Authorization": f"Bearer {BASE44_SERVICE_KEY}"}
    
    try:
        with open(local_file_path, 'rb') as f:
            files = {'file': (filename, f)}
            response = requests.post(url, files=files, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("file_url")
    except Exception as e:
        print(f"✗ Erreur upload: {e}")
        return None

def process_separation(file_url, mode, separation_id):
    """Traite la séparation audio"""
    try:
        progress_store[separation_id] = {"progress": 0, "step": "Téléchargement du fichier"}
        
        # Télécharger le fichier
        local_file = download_file(file_url)
        progress_store[separation_id] = {"progress": 15, "step": "Téléchargement du fichier"}
        
        # Initialiser Spleeter
        stem_count = 2 if mode == "2stems" else 4 if mode == "4stems" else 5
        separator = Separator(f"spleeter:{stem_count}stems")
        progress_store[separation_id] = {"progress": 30, "step": "Analyse de la piste audio"}
        
        # Séparer
        output_dir = f"/tmp/output_{separation_id}"
        separator.separate_to_file(local_file, output_dir)
        progress_store[separation_id] = {"progress": 70, "step": "Séparation des instruments"}
        
        # Upload les stems
        stems_dir = Path(output_dir) / Path(local_file).stem
        stems = {}
        stem_files = list(stems_dir.glob("*.wav"))
        
        for i, stem_file in enumerate(stem_files):
            stem_name = stem_file.stem
            stem_url = upload_to_base44(str(stem_file), f"{separation_id}_{stem_name}.wav")
            if stem_url:
                stems[stem_name] = stem_url
            progress_store[separation_id] = {"progress": 70 + (i * 20 // len(stem_files)), "step": "Génération des pistes"}
        
        # Détecter les stems
        detected_stems = list(stems.keys())
        
        # Finaliser
        progress_store[separation_id] = {"progress": 95, "step": "Finalisation"}
        update_separation(separation_id, {
            "status": "done",
            "stems": stems,
            "detected_stems": detected_stems
        })
        
        # 100% SEULEMENT quand tout est vraiment terminé
        progress_store[separation_id] = {"progress": 100, "step": "Terminé !"}
        print(f"✓ Séparation {separation_id} terminée")
        
    except Exception as e:
        print(f"✗ Erreur: {e}")
        update_separation(separation_id, {"status": "error"})
        progress_store[separation_id] = {"progress": 0, "step": "Erreur"}

@app.route("/separate", methods=["POST"])
def separate():
    data = request.json
    file_url = data.get("file_url")
    mode = data.get("mode", "2stems")
    separation_id = data.get("separation_id")
    
    if not file_url or not separation_id:
        return jsonify({"error": "file_url et separation_id requis"}), 400
    
    # Lancer en arrière-plan
    thread = threading.Thread(target=process_separation, args=(file_url, mode, separation_id))
    thread.daemon = True
    thread.start()
    
    return jsonify({"message": "Traitement lancé", "id": separation_id}), 202

@app.route("/progress/<separation_id>", methods=["GET"])
def get_progress(separation_id):
    progress = progress_store.get(separation_id, {"progress": 0, "step": "Attente"})
    return jsonify(progress)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
