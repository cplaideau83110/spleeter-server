FROM python:3.8

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Script pour pré-télécharger les modèles
RUN mkdir -p /root/.cache/spleeter && python << 'EOF'
import requests
import tarfile
import os
from pathlib import Path

cache_dir = Path.home() / '.cache' / 'spleeter'
cache_dir.mkdir(parents=True, exist_ok=True)

for model in ['2stems', '4stems', '5stems']:
    model_dir = cache_dir / model
    if model_dir.exists():
        print(f'✓ {model} déjà présent')
        continue
    
    url = f'https://github.com/deezer/spleeter/releases/download/v1.4.0/{model}.tar.gz'
    tar_path = cache_dir / f'{model}.tar.gz'
    
    print(f'📥 Téléchargement {model}...')
    r = requests.get(url, allow_redirects=True, timeout=60)
    r.raise_for_status()
    tar_path.write_bytes(r.content)
    
    print(f'📦 Extraction {model}...')
    with tarfile.open(tar_path) as tar:
        tar.extractall(cache_dir)
    tar_path.unlink()
    print(f'✓ {model} OK')
EOF

CMD ["python", "server.py"]
