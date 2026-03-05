import os
os.environ['SPLEETER_MODELS_DIR'] = '/app/.spleeter'

import json
import logging
import threading
import time
import subprocess
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import requests
from spleeter.separator import Separator
import librosa
from pathlib import Path
import tempfile
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# PRÉ-CHARGE LES MODÈLES AU DÉMARRAGE
print("⏳ Pré-chargement des modèles Spleeter...", flush=True)
separator_cache = {}
try:
    separator_cache['2stems'] = Separator('spleeter:2stems')
    print("✓ Modèle 2stems prêt", flush=True)
except Exception as e:
    print(f"⚠️ Erreur chargement 2stems: {e}", flush=True)

try:
    separator_cache['4stems'] = Separator('spleeter:4stems')
    print("✓ Modèle 4stems prêt", flush=True)
except Exception as e:
    print(f"⚠️ Erreur chargement 4stems: {e}", flush=True)

try:
    separator_cache['5stems'] = Separator('spleeter:5stems')
    print("✓ Modèle 5stems prêt", flush=True)
except Exception as e:
    print(f"⚠️ Erreur chargement 5stems: {e}", flush=True)

print("✅ Tous les modèles prêts!", flush=True)

UPLOAD_FOLDER = tempfile.gettempdir()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

progress_store = {}

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def set_progress(separation_id, progress, step=""):
    progress_store[separation_id] = {
        "progress": progress,
        "step": step,
        "status": "processing",
        "detected_stems": []
    }
    print(f"📊 {separation_id}: {progress}% - {step}", flush=True)

def get_separator(stems):
    key = f'{stems}stems'
    if key in separator_cache:
        print(f"✓ Séparateur {key} utilisé depuis le cache", flush=True)
        return separator_cache[key]
    separator_cache[key] = Separator(f'spleeter:{key}')
    return separator_cache[key]

@app.route('/separate', methods=['POST', 'OPTIONS'])
def separate():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        file_url = data.get('file_url')
        mode = data.get('mode', '4stems')
        separation_id = data.get('separation_id')

        print(f"\n🎵 POST /separate reçu!", flush=True)
        print(f"   Séparation #{separation_id}", flush=True)
        print(f"   Mode: {mode}", flush=True)

        if not all([file_url, separation_id]):
            return jsonify({"error": "Missing file_url or separation_id"}), 400

        set_progress(separation_id, 5, "Téléchargement du fichier")

        response = requests.get(file_url, timeout=300)
        if response.status_code != 200:
            raise Exception(f"Impossible de télécharger le fichier (HTTP {response.status_code})")

        temp_audio = os.path.join(UPLOAD_FOLDER, f"temp_{separation_id}.mp3")
        with open(temp_audio, 'wb') as f:
            f.write(response.content)
        print(f"✓ Fichier téléchargé: {os.path.getsize(temp_audio) / (1024 * 1024):.1f} MB", flush=True)

        set_progress(separation_id, 15, "Analyse de la piste audio")

        stem_count = 2 if mode == "2stems" else 4 if mode == "4stems" else 5
        separator = get_separator(stem_count)
        print(f"✓ Séparateur prêt ({stem_count} stems)", flush=True)

        set_progress(separation_id, 25, "Séparation des instruments")

        output_dir = os.path.join(UPLOAD_FOLDER, f"output_{separation_id}")
        os.makedirs(output_dir, exist_ok=True)

        print(f"🔄 Séparation en cours...", flush=True)
        
        stop_progress = {'value': False}

        def update_progress_thread():
            for i in range(26, 75, 5):
                if stop_progress['value']:
                    break
                time.sleep(8)
                set_progress(separation_id, i, "Séparation des instruments")
        
        t = threading.Thread(target=update_progress_thread, daemon=True)
        t.start()

        prediction = separator.separate_to_file(temp_audio, output_dir)
        stop_progress['value'] = True
        print(f"✓ Séparation terminée", flush=True)

        stems_dir = os.path.join(output_dir, f"temp_{separation_id}")
        detected_stems = sorted([f[:-4] for f in os.listdir(stems_dir) if f.endswith('.wav')]) if os.path.exists(stems_dir) else []
        print(f"✓ Stems détectés: {detected_stems}", flush=True)

        progress_store[separation_id]["detected_stems"] = detected_stems
        set_progress(separation_id, 75, "Conversion en MP3")

        for stem in detected_stems:
            wav_path = os.path.join(stems_dir, f"{stem}.wav")
            mp3_path = os.path.join(stems_dir, f"{stem}.mp3")

            try:
                subprocess.run([
                    'ffmpeg', '-i', wav_path, '-q:a', '5', '-y', mp3_path
                ], capture_output=True, check=True, timeout=300)
                print(f"   ✓ {stem}.mp3 créé", flush=True)
            except Exception as e:
                print(f"   ❌ Erreur conversion {stem}: {e}", flush=True)

        progress_store[separation_id]["progress"] = 100
        progress_store[separation_id]["status"] = "done"
        print(f"✓ Séparation #{separation_id} complète!", flush=True)

        if os.path.exists(temp_audio):
            os.remove(temp_audio)

        return jsonify({"status": "processing", "detected_stems": detected_stems}), 200

    except Exception as e:
        print(f"❌ Erreur: {e}", flush=True)
        if separation_id:
            progress_store[separation_id] = {"status": "error", "error": str(e), "progress": 0, "step": "Erreur"}
        return jsonify({"error": str(e)}), 500

@app.route('/progress/<separation_id>', methods=['GET'])
def get_progress(separation_id):
    if separation_id in progress_store:
        return jsonify(progress_store[separation_id]), 200
    return jsonify({"status": "not_found"}), 404

@app.route('/stems/<separation_id>/<stem_name>.mp3', methods=['GET'])
def get_stem(separation_id, stem_name):
    try:
        mp3_path = os.path.join(UPLOAD_FOLDER, f"output_{separation_id}", f"temp_{separation_id}", f"{stem_name}.mp3")
        if os.path.exists(mp3_path):
            return send_file(mp3_path, mimetype='audio/mpeg', as_attachment=False)
        return jsonify({"error": "Fichier non trouvé"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
