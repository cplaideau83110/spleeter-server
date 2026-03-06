from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import threading
import os
import uuid
import requests
import subprocess
import json

app = Flask(__name__)
CORS(app)

# Config Base44
BASE44_APP_ID = "69a8f857a6a0fa216be33357"
BASE44_API_KEY = "cafa03f1b09c4e3d9aee529253d3478c"

# Stockage des progressions en mémoire
progress_store = {}

# Cache du séparateur Spleeter
separator_cache = {}

def download_file(url, dest_path):
    """Télécharge un fichier depuis une URL (suit les redirections)"""
    response = requests.get(url, stream=True, allow_redirects=True)
    response.raise_for_status()
    with open(dest_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    size_mb = os.path.getsize(dest_path) / (1024 * 1024)
    print(f"✓ Fichier téléchargé: {size_mb:.1f} MB")
    return dest_path
def upload_to_base44(file_path, filename):
    """Upload un fichier vers Base44 et retourne l'URL publique"""
    url = f"https://api.base44.app/api/apps/{BASE44_APP_ID}/integrations/invoke"
    with open(file_path, 'rb') as f:
        response = requests.post(
            url,
            data={"integration_name": "Core", "method_name": "UploadFile"},
            files={"file": (filename, f, "audio/mpeg")},
            headers={"api-key": BASE44_API_KEY}
        )
    print(f"Upload response: {response.status_code} - {response.text[:200]}")
    response.raise_for_status()
    data = response.json()
    return data["file_url"]

def update_separation_in_base44(separation_id, update_data):
    """Met à jour une entité Separation dans Base44"""
    url = f"https://api.base44.app/api/apps/{BASE44_APP_ID}/entities/Separation/{separation_id}"
    response = requests.put(
        url,
        json=update_data,
        headers={
            "api-key": BASE44_API_KEY,
            "Content-Type": "application/json"
        }
    )
    print(f"Update response: {response.status_code} - {response.text}")
    response.raise_for_status()
    return response.json()

def process_separation(separation_id, file_url, mode):
    """Traitement principal de la séparation audio"""
    tmp_dir = f"/tmp/output_{separation_id}"
    os.makedirs(tmp_dir, exist_ok=True)
    input_path = f"{tmp_dir}/input.mp3"

    try:
        # 1. Téléchargement
        progress_store[separation_id] = {"status": "processing", "progress": 5, "step": "Téléchargement du fichier", "detected_stems": []}
        print(f"📊 {separation_id}: 5% - Téléchargement du fichier")
        download_file(file_url, input_path)

        # 2. Chargement du séparateur
        progress_store[separation_id]["progress"] = 15
        progress_store[separation_id]["step"] = "Analyse de la piste audio"
        print(f"📊 {separation_id}: 15% - Analyse de la piste audio")

        from spleeter.separator import Separator

        stems_map = {
            "2stems": 2,
            "4stems": 4,
            "5stems": 5,
        }
        n_stems = stems_map.get(mode, 4)
        spleeter_model = f"spleeter:{n_stems}stems"

        if spleeter_model not in separator_cache:
            separator_cache[spleeter_model] = Separator(spleeter_model)
            print(f"✓ Séparateur {n_stems}stems chargé")
        else:
            print(f"✓ Séparateur {n_stems}stems utilisé depuis le cache")

        separator = separator_cache[spleeter_model]
        print(f"✓ Séparateur prêt ({n_stems} stems)")

        # 3. Séparation
        progress_store[separation_id]["progress"] = 25
        progress_store[separation_id]["step"] = "Séparation des instruments"
        print(f"📊 {separation_id}: 25% - Séparation des instruments")

        output_dir = f"{tmp_dir}/temp_{separation_id}"
        os.makedirs(output_dir, exist_ok=True)

        print("🔄 Séparation en cours...")
        separator.separate_to_file(input_path, output_dir)
        print("✓ Séparation terminée")

        # 4. Détection des stems
        stem_subdir = os.path.join(output_dir, "input")
        if os.path.exists(stem_subdir):
            wav_files = [f for f in os.listdir(stem_subdir) if f.endswith(".wav")]
        else:
            wav_files = [f for f in os.listdir(output_dir) if f.endswith(".wav")]
            stem_subdir = output_dir

        detected_stems = [os.path.splitext(f)[0] for f in wav_files]
        print(f"✓ Stems détectés: {detected_stems}")

        progress_store[separation_id]["detected_stems"] = detected_stems

        # 5. Conversion WAV → MP3
        progress_store[separation_id]["progress"] = 75
        progress_store[separation_id]["step"] = "Conversion en MP3"
        print(f"📊 {separation_id}: 75% - Conversion en MP3")

        mp3_paths = {}
        for stem_name in detected_stems:
            wav_path = f"{stem_subdir}/{stem_name}.wav"
            mp3_path = f"{tmp_dir}/{stem_name}.mp3"
            subprocess.run(
                ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_path],
                check=True, capture_output=True
            )
            print(f"   ✓ {stem_name}.mp3 créé")
            mp3_paths[stem_name] = mp3_path

        # 6. Upload vers Base44
        progress_store[separation_id]["progress"] = 85
        progress_store[separation_id]["step"] = "Upload des stems"
        print(f"📊 {separation_id}: 85% - Upload des stems vers Base44")

        stem_urls = {}
        for stem_name, mp3_path in mp3_paths.items():
            print(f"   ⬆️ Upload {stem_name}.mp3 vers Base44...")
            url = upload_to_base44(mp3_path, f"{stem_name}.mp3")
            stem_urls[stem_name] = url
            print(f"   ✓ {stem_name} uploadé: {url}")

        # 7. Mise à jour Base44 avec les URLs permanentes
        progress_store[separation_id]["progress"] = 95
        progress_store[separation_id]["step"] = "Finalisation"
        print(f"📊 {separation_id}: 95% - Finalisation")

        update_separation_in_base44(separation_id, {
            "status": "done",
            "stems": stem_urls,
            "detected_stems": detected_stems
        })
        print(f"✓ Base44 mis à jour avec les URLs des stems")

        # 8. Done
        progress_store[separation_id]["status"] = "done"
        progress_store[separation_id]["progress"] = 100
        progress_store[separation_id]["step"] = "Séparation complète"
        print(f"✓ Séparation #{separation_id} complète!")

    except Exception as e:
        print(f"❌ Erreur séparation {separation_id}: {e}")
        progress_store[separation_id] = {"status": "error", "progress": 0, "step": str(e), "detected_stems": []}
        try:
            update_separation_in_base44(separation_id, {"status": "error"})
        except:
            pass

    finally:
        import shutil
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
            print(f"🧹 Dossier temporaire supprimé")


@app.route("/separate", methods=["POST"])
def separate():
    data = request.json
    file_url = data.get("file_url")
    mode = data.get("mode", "4stems")
    separation_id = data.get("separation_id")

    if not file_url or not separation_id:
        return jsonify({"error": "file_url et separation_id requis"}), 400

    progress_store[separation_id] = {"status": "processing", "progress": 0, "step": "Démarrage", "detected_stems": []}

    thread = threading.Thread(target=process_separation, args=(separation_id, file_url, mode))
    thread.daemon = True
    thread.start()

    return jsonify({"status": "processing", "separation_id": separation_id})


@app.route("/progress/<separation_id>", methods=["GET"])
def progress(separation_id):
    info = progress_store.get(separation_id, {"status": "unknown", "progress": 0, "step": "Inconnu", "detected_stems": []})
    return jsonify(info)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
