import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
from pathlib import Path
import shutil
import gc
from pydub import AudioSegment

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

BASE44_APP_ID = os.environ.get("BASE44_APP_ID", "69a8f857a6a0fa216be33357")
BASE44_API_URL = "https://api.base44.com/api/apps"

progress_store = {}
SEPARATOR = None

def get_separator(stem_count):
    global SEPARATOR
    if SEPARATOR is None:
        print("📦 Chargement du modèle Spleeter...")
        from spleeter.separator import Separator
        SEPARATOR = Separator(f"spleeter:{stem_count}stems")
        print("✓ Modèle chargé et prêt")
    return SEPARATOR

def set_progress(separation_id, progress, step):
    progress_store[separation_id] = {"progress": progress, "step": step}
    print(f"[{progress}%] {step}")

def update_separation(separation_id, data):
    url = f"{BASE44_API_URL}/{BASE44_APP_ID}/entities/Separation/{separation_id}"
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.patch(url, json=data, headers=headers, timeout=10)
        response.raise_for_status()
        print(f"✓ Base44 mis à jour")
        return True
    except Exception as e:
        print(f"✗ Erreur update Base44: {e}")
        return False

def convert_wav_to_mp3(wav_path, mp3_path):
    try:
        print(f"    🔄 Conversion WAV → MP3...")
        audio = AudioSegment.from_wav(wav_path)
        audio.export(mp3_path, format="mp3", bitrate="192k")
        wav_size = os.path.getsize(wav_path) / 1024 / 1024
        mp3_size = os.path.getsize(mp3_path) / 1024 / 1024
        print(f"    ✓ Converti: {wav_size:.1f}MB → {mp3_size:.1f}MB")
        return True
    except Exception as e:
        print(f"    ✗ Erreur conversion: {e}")
        return False

def upload_stem_file(stem_path, filename):
    try:
        print(f"    🔍 Vérification: {stem_path}")
        if not os.path.exists(stem_path):
            print(f"    ❌ Fichier n'existe pas!")
            return None
        
        file_size = os.path.getsize(stem_path)
        print(f"    📦 Fichier: {file_size / 1024 / 1024:.1f} MB")
        
        with open(stem_path, 'rb') as f:
            files = {'file': (filename, f, 'audio/mpeg')}
            url = f"{BASE44_API_URL}/{BASE44_APP_ID}/files/upload"
            print(f"    🌐 Upload...")
            response = requests.post(url, files=files, timeout=30)
            print(f"    📊 Status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            file_url = data.get('file_url')
            print(f"    ✓ URL: {file_url}")
            return file_url
    except Exception as e:
        print(f"    ✗ Exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

def process_separation(file_url, mode, separation_id):
    local_path = None
    output_dir = None
    try:
        print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"🎵 Traitement: {separation_id}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        
        set_progress(separation_id, 5, "Téléchargement du fichier")
        print(f"📥 Téléchargement...")
        response = requests.get(file_url, stream=True, timeout=30)
        response.raise_for_status()
        
        local_path = f"/tmp/{separation_id}.mp3"
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        file_size = os.path.getsize(local_path)
        print(f"✓ Fichier téléchargé ({file_size / 1024 / 1024:.1f} MB)\n")
        
        set_progress(separation_id, 20, "Initialisation du séparateur")
        print(f"⚙️ Initialisation Spleeter...")
        stem_count = 2 if mode == "2stems" else 4 if mode == "4stems" else 5
        separator = get_separator(stem_count)
        print(f"✓ Séparateur prêt ({stem_count} stems)\n")
        
        disk = shutil.disk_usage("/tmp")
        print(f"📊 Espace disque /tmp: {disk.free / 1024 / 1024 / 1024:.2f} GB\n")
        
        set_progress(separation_id, 35, "Séparation des instruments")
        print(f"🔊 Séparation en cours...")
        output_dir = f"/tmp/output_{separation_id}"
        separator.separate_to_file(local_path, output_dir)
        print(f"✓ Séparation terminée\n")
        
        set_progress(separation_id, 70, "Récupération des pistes")
        print(f"📂 Dossier stems...")
        stems_dir = Path(output_dir) / Path(local_path).stem
        stem_files = sorted(stems_dir.glob("*.wav"))
        detected_stems = [f.stem for f in stem_files]
        print(f"✓ Trouvé: {', '.join(detected_stems)}\n")
        
        set_progress(separation_id, 75, "Conversion en MP3")
        print(f"🎚️ Conversion des pistes...")
        mp3_files = {}
        for stem_file in stem_files:
            stem_name = stem_file.stem
            mp3_path = stem_file.with_suffix('.mp3')
            if convert_wav_to_mp3(str(stem_file), str(mp3_path)):
                mp3_files[stem_name] = mp3_path
        print()
        
        set_progress(separation_id, 80, "Upload des pistes")
        print(f"📤 Upload des fichiers MP3...")
        stems = {}
        for stem_name, mp3_path in mp3_files.items():
            filename = f"{separation_id}_{stem_name}.mp3"
            print(f"  📤 Upload {filename}...")
            file_url = upload_stem_file(str(mp3_path), filename)
            if file_url:
                stems[stem_name] = file_url
            else:
                print(f"  ✗ Échec upload {filename}")
        
        if not stems:
            print(f"❌ Aucun stem uploadé!")
            raise Exception("Aucun stem uploadé")
        print(f"✓ Upload terminé ({len(stems)} pistes)\n")
        
        set_progress(separation_id, 90, "Finalisation")
        print(f"💾 Enregistrement en base...")
        success = update_separation(separation_id, {
            "status": "done",
            "stems": stems,
            "detected_stems": detected_stems
        })
        
        if success:
            set_progress(separation_id, 100, "Terminé !")
            print(f"✓✓✓ SUCCÈS !\n")
            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
        
    except Exception as e:
        print(f"\n✗✗✗ ERREUR: {e}\n")
        import traceback
        traceback.print_exc()
        set_progress(separation_id, 0, "Erreur")
        update_separation(separation_id, {"status": "error"})
    
    finally:
        if local_path and os.path.exists(local_path):
            os.remove(local_path)
            print(f"🧹 Fichier entrée supprimé")
        
        if output_dir and os.path.exists(output_dir):
            shutil.rmtree(output_dir)
            print(f"🧹 Dossier sortie supprimé")
        
        gc.collect()
        print(f"🧹 Mémoire libérée\n")

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
