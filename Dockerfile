FROM python:3.8-slim

WORKDIR /app

# Installe les dépendances système
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copie requirements.txt
COPY requirements.txt .

# Installe les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# PRÉ-CHARGE LES MODÈLES SPLEETER
ENV SPLEETER_MODELS_DIR=/app/.spleeter
RUN python -c "from spleeter.separator import Separator; print('Pré-chargement 2stems...'); Separator('spleeter:2stems'); print('✓'); print('Pré-chargement 4stems...'); Separator('spleeter:4stems'); print('✓'); print('Pré-chargement 5stems...'); Separator('spleeter:5stems'); print('✓ Done!')"

# Copie le code
COPY server.py .

# Lance l'app
CMD ["python", "server.py"]
