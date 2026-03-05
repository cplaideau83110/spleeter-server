FROM tensorflow/tensorflow:2.12.0

RUN apt-get update && apt-get install -y ffmpeg libsndfile1

WORKDIR /app
COPY requirements.txt .
RUN pip install flask flask-cors spleeter requests

COPY server.py .

CMD ["python", "server.py"]
