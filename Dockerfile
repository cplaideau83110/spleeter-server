FROM python:3.8-slim

RUN apt-get update && apt-get install -y ffmpeg libsndfile1

WORKDIR /app

RUN pip install --no-cache-dir \
    protobuf==3.20.3 \
    tensorflow==2.12.0 \
    werkzeug==2.2.3 \
    flask==2.2.5 \
    flask-cors==4.0.0 \
    requests \
    spleeter

COPY server.py .

CMD ["python", "server.py"]
