FROM python:3.8

WORKDIR /app

# Installer ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-deps spleeter==2.3.0 && pip install Flask==2.2.0 Werkzeug==2.2.0 flask-cors==4.0.0 pydub==0.25.1 requests==2.31.0 numpy librosa tensorflow==2.5.0 pandas typer==0.9.0 ffmpeg-python "httpx[http2]"

# Pré-télécharger les modèles spleeter pour éviter les redirects à l'exécution
RUN python -c "from spleeter.separator import Separator; Separator('spleeter:4stems')" && \
    python -c "from spleeter.separator import Separator; Separator('spleeter:2stems')" && \
    python -c "from spleeter.separator import Separator; Separator('spleeter:5stems')"

# Copier l'app
COPY . .

# Lancer l'app
CMD ["python", "server.py"]
