import os
import json
import logging
from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import requests
from spleeter.separator import Separator
import librosa
import soundfile as sf
from pathlib import Path
import tempfile
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # ← AJOUTE CETTE LIGNE

UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'flac', 'ogg'}

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
    """Initialise et retourne un séparateur Spleeter"""
    print(f"⚙️ Chargement modèle {stems}stems...", flush=True)
    return Separator(f'spleeter:{stems}stems')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/separate', methods=['POST', 'OPTIONS'])  # ← AJOUTE OPTIONS
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
        print(f"   URL: {file_url}", flush=True)

        if not all([file_url, separation_id]):
            return jsonify({"error": "Missing file_url or separation_id"}), 400

        set_progress(separation_id, 5, "Téléchargement du fichier")

        # Télécharge le fichier
        response = requests.get(file_url, timeout=300)
        if response.status_code != 200:
            raise Exception(f"Impossible de télécharger le fichier (HTTP {response.status_code})")

        # Sauvegarde temporaire
        temp_audio = os.path.join(UPLOAD_FOLDER, f"temp_{separation_id}.mp3")
        with open(temp_audio, 'wb') as f:
            f.write(response.content)
        file_size = os.path.getsize(temp_audio) / (1024 * 1024)
        print(f"✓ Fichier téléchargé: {file_size:.1f} MB", flush=True)

        set_progress(separation_id, 15, "Analyse de la piste audio")

        # Charge le séparateur Spleeter
        stem_count = 2 if mode == "2stems" else 4 if mode == "4stems" else 5
        print(f"⚙️ Initialisation Spleeter {stem_count}stems...", flush=True)
        separator = get_separator(stem_count)
        print(f"✓ Séparateur prêt ({stem_count} stems)", flush=True)

        set_progress(separation_id, 25, "Séparation des instruments")

        # Crée répertoire de sortie
        output_dir = os.path.join(UPLOAD_FOLDER, f"output_{separation_id}")
        os.makedirs(output_dir, exist_ok=True)

        # Sépare les pistes
        print(f"🔄 Séparation en cours...", flush=True)
        prediction = separator.separate_to_file(temp_audio, output_dir)
        print(f"✓ Séparation terminée", flush=True)

        # Liste les stems générés
        stems_dir = os.path.join(output_dir, "temp_audio")
        detected_stems = []
        if os.path.exists(stems_dir):
            wav_files = [f[:-4] for f in os.listdir(stems_dir) if f.endswith('.wav')]
            detected_stems = sorted(wav_files)
            print(f"✓ Stems détectés: {detected_stems}", flush=True)
        else:
            print(f"⚠️ Répertoire de sortie non trouvé: {stems_dir}", flush=True)
            return jsonify({"error": "Séparation échouée"}), 500

        # Met à jour le statut avec les stems détectés
        progress_store[separation_id] = {
            "progress": 50,
            "step": "Génération des pistes",
            "status": "processing",
            "detected_stems": detected_stems
        }
        print(f"📊 Stems détectés stockés: {detected_stems}", flush=True)

        set_progress(separation_id, 75, "Conversion en MP3")

        # Convertit en MP3
        for stem in detected_stems:
            wav_path = os.path.join(stems_dir, f"{stem}.wav")
            mp3_path = os.path.join(stems_dir, f"{stem}.mp3")

            print(f"   🔄 Conversion {stem}.wav → {stem}.mp3...", flush=True)

            try:
                y, sr = librosa.load(wav_path, sr=None)
                sf.write(mp3_path, y, sr, subtype='PCM_16')
                print(f"   ✓ {stem}.mp3 créé", flush=True)
            except Exception as e:
                print(f"   ❌ Erreur conversion {stem}: {e}", flush=True)

        progress_store[separation_id]["progress"] = 90
        progress_store[separation_id]["step"] = "Finalisation"

        # Marque comme done
        progress_store[separation_id]["status"] = "done"
        print(f"✓ Séparation #{separation_id} complète!", flush=True)

        # Nettoyage
        if os.path.exists(temp_audio):
            os.remove(temp_audio)

        return jsonify({"status": "processing", "detected_stems": detected_stems}), 200

    except Exception as e:
        print(f"❌ Erreur: {e}", flush=True)
        if separation_id:
            progress_store[separation_id] = {
                "status": "error",
                "error": str(e),
                "progress": 0,
                "step": "Erreur"
            }
        return jsonify({"error": str(e)}), 500

@app.route('/progress/<separation_id>', methods=['GET'])
def get_progress(separation_id):
    """Retourne le statut et les stems détectés"""
    print(f"📥 GET /progress/{separation_id}", flush=True)
    if separation_id in progress_store:
        print(f"✓ Trouvé: {progress_store[separation_id]}", flush=True)
        return jsonify(progress_store[separation_id]), 200
    print(f"❌ Pas trouvé en mémoire", flush=True)
    return jsonify({"status": "not_found"}), 404

@app.route('/stems/<separation_id>/<stem_name>.mp3', methods=['GET'])
def get_stem(separation_id, stem_name):
    """Télécharge un stem en MP3"""
    try:
        mp3_path = os.path.join(UPLOAD_FOLDER, f"output_{separation_id}", "temp_audio", f"{stem_name}.mp3")
        print(f"📥 GET /stems/{separation_id}/{stem_name}.mp3 → {mp3_path}", flush=True)
        if os.path.exists(mp3_path):
            print(f"✓ Fichier trouvé", flush=True)
            return send_file(mp3_path, mimetype='audio/mpeg', as_attachment=False)
        else:
            print(f"❌ Fichier non trouvé", flush=True)
            return jsonify({"error": "Fichier non trouvé"}), 404
    except Exception as e:
        print(f"❌ Erreur: {e}", flush=True)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
