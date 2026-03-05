FROM python:3.8-slim

RUN apt-get update && apt-get install -y ffmpeg libsndfile1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir \
    flask \
    flask-cors \
    requests \
    protobuf==3.20.3 \
    tensorflow==2.12.0 \
    spleeter

COPY server.py .

CMD ["python", "server.py"]
