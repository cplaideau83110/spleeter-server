import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import base64

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BASE44_APP_ID = os.environ.get("BASE44_APP_ID", "69a8f857a6a0fa216be33357")
BASE44_SERVICE_KEY = os.environ.get("BASE44_SERVICE_KEY", "")
BASE44_API_URL = "https://api.base44.com/api/apps"

progress_store = {}

def update_separation(separation_id, data):
    url = f"{BASE44_API_URL}/{BASE44_APP_ID}/entities/Separation/{separation_id}"
    headers = {
        "Authorization": f"Bearer {BASE44_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.patch(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()
        print(f"✓ Séparation {separation_id} mise à jour")
        return True
    except Exception as e:
        print(f"✗ Erreur update: {e}")
        return False

def invoke_backend_function(function_name, payload):
    """Appelle une backend function Base44"""
    url = f"{BASE44_API_URL}/{BASE44_APP_ID}/functions/{function_name}/invoke"
    headers = {
        "Authorization": f"Bearer {BASE44_SERVICE_KEY}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"✗ Erreur fonction {function_name}: {e}")
        return None

def process_separation(file_url, mode, separation_id):
    try:
        print(f"🎵 Début {separation_id}")
        
        from spleeter.separator import Separator
        from pathlib import Path
        
        progress_store[separation_id] = {"progress": 5, "step": "Téléchargement"}
        
        response = requests.get(file_url, stream=True, timeout=30)
        response.raise_for_status()
        
        local_path = f"/tmp/{separation_id}.mp3"
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"✓ Téléchargé ({os.path.getsize(local_path)} bytes)")
        progress_store[separation_id] = {"progress": 25, "step": "Séparation"}
        
        stem_count = 2 if mode == "2stems" else 4 if mode == "4stems" else 5
        separator = Separator(f"spleeter:{stem_count}stems")
        output_dir = f"/tmp/output_{separation_id}"
        
        separator.separate_to_file(local_path, output_dir)
        
        print(f"✓ Séparation {stem_count}stems terminée")
        progress_store[separation_id] = {"progress": 75, "step": "Upload des pistes"}
        
        stems_dir = Path(output_dir) / Path(local_path).stem
        stems = {}
        stem_files = sorted(stems_dir.glob("*.wav"))
        detected_stems = [f.stem for f in stem_files]
        
        print(f"Stems: {detected_stems}")
        
        # Upload chaque stem via backend function
        for stem_file in stem_files:
            stem_name = stem_file.stem
            print(f"📤 Upload {stem_name}...")
            
            try:
                with open(stem_file, 'rb') as f:
                    file_content = f.read()
                    file_b64 = base64.b64encode(file_content).decode('utf-8')
                    
                    # Appeler la backend function uploadStem
                    result = invoke_backend_function("uploadStem", {
                        "filename": f"{separation_id}_{stem_name}.wav",
                        "file_b64": file_b64
                    })
                    
                    if result and "file_url" in result:
                        stems[stem_name] = result["file_url"]
                        print(f"✓ {stem_name}: {result['file_url']}")
                    else:
                        print(f"✗ Upload échoué pour {stem_name}")
            except Exception as e:
                print(f"✗ Erreur {stem_name}: {e}")
        
        if not stems:
            raise Exception("Aucun stem uploadé")
        
        progress_store[separation_id] = {"progress": 95, "step": "Finalisation"}
        
        success = update_separation(separation_id, {
            "status": "done",
            "stems": stems,
            "detected_stems": detected_stems
        })
        
        if success:
            progress_store[separation_id] = {"progress": 100, "step": "Terminé !"}
            print(f"✓✓✓ {separation_id} TERMINÉ")
        
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
