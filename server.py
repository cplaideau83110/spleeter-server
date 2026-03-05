import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
from pathlib import Path

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BASE44_APP_ID = os.environ.get("BASE44_APP_ID", "69a8f857a6a0fa216be33357")
BASE44_API_URL = "https://api.base44.com/api/apps"

progress_store = {}
SEPARATOR = None  # Global singleton

def get_separator(stem_count):
    """Charge le modèle une seule fois et le réutilise"""
    global SEPARATOR
    if SEPARATOR is None:
        from spleeter.separator import Separator
        SEPARATOR = Separator(f"spleeter:{stem_count}stems")
    return SEPARATOR

def update_separation(separation_id, data):
    url = f"{BASE44_API_URL}/{BASE44_APP_ID}/entities/Separation/{separation_id}"
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.patch(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()
        print(f"✓ Mise à jour: {separation_id}")
        return True
    except Exception as e:
        print(f"✗ Erreur update: {e}")
        return False

def upload_stem_file(stem_path, filename):
    try:
        with open(stem_path, 'rb') as f:
            files = {'file': (filename, f, 'audio/wav')}
            url = f"{BASE44_API_URL}/{BASE44_APP_ID}/files/upload"
            response = requests.post(url, files=files, timeout=30)
            response.raise_for_status()
            data = response.json()
            file_url = data.get('file_url')
            print(f"✓ Upload: {filename}")
            return file_url
    except Exception as e:
        print(f"✗ Upload {filename}: {e}")
        return None

def process_separation(file_url, mode, separation_id):
    try:
        print(f"🎵 Début {separation_id}")
        
        progress_store[separation_id] = {"progress": 5, "step": "Téléchargement"}
        response = requests.get(file_url, stream=True, timeout=30)
        response.raise_for_status()
        
        local_path = f"/tmp/{separation_id}.mp3"
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"✓ Téléchargé")
        progress_store[separation_id] = {"progress": 25, "step": "Séparation"}
        
        stem_count = 2 if mode == "2stems" else 4 if mode == "4stems" else 5
        separator = get_separator(stem_count)  # Réutilise le modèle
        output_dir = f"/tmp/output_{separation_id}"
        separator.separate_to_file(local_path, output_dir)
        
        print(f"✓ Séparation {stem_count}stems")
        progress_store[separation_id] = {"progress": 75, "step": "Upload"}
        
        stems_dir = Path(output_dir) / Path(local_path).stem
        stems = {}
        stem_files = sorted(stems_dir.glob("*.wav"))
        detected_stems = [f.stem for f in stem_files]
        
        print(f"Stems: {detected_stems}")
        
        for stem_file in stem_files:
            stem_name = stem_file.stem
            filename = f"{separation_id}_{stem_name}.wav"
            file_url = upload_stem_file(str(stem_file), filename)
            if file_url:
                stems[stem_name] = file_url
        
        if not stems:
            raise Exception("Aucun stem uploadé")
        
        success = update_separation(separation_id, {
            "status": "done",
            "stems": stems,
            "detected_stems": detected_stems
        })
        
        if success:
            print(f"✓✓✓ TERMINÉ")
            progress_store[separation_id] = {"progress": 100, "step": "Terminé !"}
        
    except Exception as e:
        print(f"✗ Erreur: {e}")
        update_separation(separation_id, {"status": "error"})

@app.route("/separate", methods=["POST"])
def separate():
    data = request.json
    file_url = data.get("file_url")
    mode = data.get("mode", "2stems")
    separation_id = data.get("separation_id")
    
    if not file_url or not separation_id:
        return jsonify({"error": "Paramètres manquants"}), 400
    
    thread = threading.Thread(target=process_separation, args=(file_url, mode, separation_id), daemon=True)
    thread.start()
    return jsonify({"status": "ok"}), 202

@app.route("/progress/<separation_id>", methods=["GET"])
def get_progress(separation_id):
    return jsonify(progress_store.get(separation_id, {"progress": 0, "step": "Attente"}))

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=True)
    
