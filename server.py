import os
import threading
import tempfile
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from spleeter.separator import Separator

app = Flask(__name__)
CORS(app)

APP_ID = os.environ.get("69a8f857a6a0fa216be33357")  # ton App ID Base44
BASE44_API_URL = f"https://api.base44.com/api/apps/{APP_ID}/entities/Separation"
BASE44_UPLOAD_URL = f"https://api.base44.com/api/apps/{APP_ID}/upload"


def process_separation(file_url, mode, separation_id, token):
    headers_json = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        # 1. Télécharger le fichier audio
        r = requests.get(file_url, timeout=60)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tmp.write(r.content)
        tmp.close()

        # 2. Séparer avec Spleeter
        out_dir = f"/tmp/stems_{separation_id}"
        separator = Separator(f"spleeter:{mode}")
        separator.separate_to_file(tmp.name, out_dir)

        # 3. Trouver les fichiers générés
        stem_folder = os.path.join(out_dir, os.path.splitext(os.path.basename(tmp.name))[0])
        stems_urls = {}

        for stem_file in os.listdir(stem_folder):
            stem_name = os.path.splitext(stem_file)[0]  # ex: "vocals", "drums"
            stem_path = os.path.join(stem_folder, stem_file)

            # 4. Uploader chaque stem sur Base44
            with open(stem_path, "rb") as f:
                upload_res = requests.post(
                    BASE44_UPLOAD_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    files={"file": (stem_file, f, "audio/wav")}
                )
            stems_urls[stem_name] = upload_res.json().get("file_url")

        # 5. Mettre à jour le statut dans Base44 → done
        requests.patch(
            f"{BASE44_API_URL}/{separation_id}",
            headers=headers_json,
            json={"status": "done", "stems": stems_urls}
        )

    except Exception as e:
        print(f"Erreur: {e}")
        requests.patch(
            f"{BASE44_API_URL}/{separation_id}",
            headers=headers_json,
            json={"status": "error"}
        )


@app.route("/separate", methods=["POST"])
def separate():
    data = request.json
    file_url = data.get("file_url")
    mode = data.get("mode", "2stems")
    separation_id = data.get("separation_id")
    token = data.get("token")

    if not file_url or not separation_id or not token:
        return jsonify({"error": "file_url, separation_id and token are required"}), 400

    threading.Thread(
        target=process_separation,
        args=(file_url, mode, separation_id, token)
    ).start()

    return jsonify({"status": "started"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

