FROM python:3.8

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-deps spleeter==2.3.0 && pip install Flask==2.2.0 flask-cors==4.0.0 pydub==0.25.1 requests==2.31.0 numpy librosa tensorflow==2.5.0 pandas

COPY . .

CMD ["python", "server.py"]
