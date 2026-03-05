FROM python:3.8

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install Flask==2.2.0 Werkzeug==2.2.0 flask-cors==4.0.0 pydub==0.25.1 requests==2.31.0 numpy==1.19.5 librosa==0.8.0 tensorflow==2.5.0 pandas==1.1.5 ffmpeg-python==0.2.0 httpx==0.19.0 h2==4.1.0 && \
    pip install --no-deps spleeter==2.3.0 && \
    pip install norbert==0.2.1

COPY . .

RUN mkdir -p /root/.cache/spleeter && python << 'EOF'
import requests
import tarfile
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
