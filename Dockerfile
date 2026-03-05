FROM python:3.8

WORKDIR /app

# Installer ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-deps spleeter==2.3.0 && pip install Flask==2.2.0 Werkzeug==2.2.0 flask-cors==4.0.0 pydub==0.25.1 requests==2.31.0 numpy librosa tensorflow==2.5.0 pandas typer==0.9.0 ffmpeg-python "httpx[http2]"

# Pré-télécharger les modèles avec requests (gère les redirects)
RUN mkdir -p /root/.spleeter/pretrained_models && \
    python -c "
import requests
import tarfile
import os

models = ['2stems', '4stems', '5stems']
for model in models:
    url = f'https://github.com/deezer/spleeter/releases/download/v1.4.0/{model}.tar.gz'
    path = f'/root/.spleeter/pretrained_models/{model}.tar.gz'
    print(f'Téléchargement {model}...')
    r = requests.get(url, allow_redirects=True)
    with open(path, 'wb') as f:
        f.write(r.content)
    print(f'Extraction {model}...')
    with tarfile.open(path) as tar:
        tar.extractall('/root/.spleeter/pretrained_models/')
    os.remove(path)
    print(f'✓ {model} OK')
"

# Copier l'app
COPY . .

# Lancer l'app
CMD ["python", "server.py"]
