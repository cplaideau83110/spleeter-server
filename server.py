import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import traceback

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BASE44_APP_ID = os.environ.get("BASE44_APP_ID", "69a8f857a6a0fa216be33357")
BASE44_SERVICE_KEY = os.environ.get("BASE44_SERVICE_KEY", "")
BASE44_API_URL = "https://api.base44.com/api/apps"

progress_store = {}

def update_separation(separation_id, data):
    """Met à jour la séparation dans Base44"""
    url = f"{BASE44_API_URL}/{BASE44_APP_ID}/entities/Separation/{separation_id}"
    headers = {
        "Authorization": f"Bearer {BASE44_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.patch(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()
        print(f"✓ Séparation {separation_id} mise à jour")
    except Exception as e:
        print(f"✗ Erreur update: {e}")

def process_separation(file_url, mode, separation_id):
    """Traite la séparation audio"""
    try:
        print(f"🎵 Début du traitement {separation_id}")
        
        # Spleeter importé ici pour éviter de bloquer le démarrage
        from spleeter.separator import Separator
        from pathlib import Path
        
        progress_store[separation_id] = {"progress": 0, "step": "Téléchargement du fichier"}
        
        # Télécharger le fichier
        print(f"📥 Téléchargement de {file_url}")
        response = requests.get(file_url, stream=True, timeout=30)
        response.raise_for_status()
        
        local_path = f"/tmp/{separation_id}.mp3"
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"✓ Fichier téléchargé ({os.path.getsize(local_path)} bytes)")
        progress_store[separation_id] = {"progress": 15, "step": "Analyse de la piste audio"}
        
        # Séparer
        stem_count = 2 if mode == "2stems" else 4 if mode == "4stems" else 5
        separator = Separator(f"spleeter:{stem_count}stems")
        progress_store[separation_id] = {"progress": 30, "step": "Séparation en cours"}
        
        output_dir = f"/tmp/output_{separation_id}"
        print(f"🎼 Séparation {stem_count}stems...")
        separator.separate_to_file(local_path, output_dir)
        
        progress_store[separation_id] = {"progress": 85, "step": "Upload des pistes"}
        
        # Upload les stems
        stems_dir = Path(output_dir) / Path(local_path).stem
        stems = {}
        stem_files = list(stems_dir.glob("*.wav"))
        detected_stems = []
        
        for stem_file in stem_files:
            stem_name = stem_file.stem
            detected_stems.append(stem_name)
            
            # Upload simple via Base44
            url_upload = f"{BASE44_API_URL}/{BASE44_APP_ID}/files/upload"
            headers = {"Authorization": f"Bearer {BASE44_SERVICE_KEY}"}
            
            with open(stem_file, 'rb') as f:
                files = {'file': (f"{separation_id}_{stem_name}.wav", f)}
                resp = requests.post(url_upload, files=files, headers=headers, timeout=30)
                if resp.ok:
                    data = resp.json()
                    stems[stem_name] = data.get("file_url")
                    print(f"✓ {stem_name} uploadé")
        
        # Finaliser
        progress_store[separation_id] = {"progress": 95, "step": "Finalisation"}
        update_separation(separation_id, {
            "status": "done",
            "stems": stems,
            "detected_stems": detected_stems
        })
        
        progress_store[separation_id] = {"progress": 100, "step": "Terminé !"}
        print(f"✓ Traitement {separation_id} terminé")
        
    except Exception as e:
        print(f"✗ Erreur: {e}")
        print(traceback.format_exc())
        update_separation(separation_id, {"status": "error"})
        progress_store[separation_id] = {"progress": 0, "step": "Erreur"}

@app.route("/separate", methods=["POST"])
def separate():
    try:
        data = request.json
        file_url = data.get("file_url")
        mode = data.get("mode", "2stems")
        separation_id = data.get("separation_id")
        
        if not file_url or not separation_id:
            return jsonify({"error": "file_url et separation_id requis"}), 400
        
        thread = threading.Thread(target=process_separation, args=(file_url, mode, separation_id))
        thread.daemon = True
        thread.start()
        
        return jsonify({"message": "Traitement lancé", "id": separation_id}), 202
    except Exception as e:
        print(f"Erreur /separate: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/progress/<separation_id>", methods=["GET"])
def get_progress(separation_id):
    progress = progress_store.get(separation_id, {"progress": 0, "step": "Attente"})
    return jsonify(progress)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    print("🚀 Serveur Spleeter démarré")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=True)
