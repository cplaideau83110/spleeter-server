FROM python:3.8

WORKDIR /app

# Installer ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copier l'app
COPY . .

# Lancer l'app
CMD ["python", "server.py"]
