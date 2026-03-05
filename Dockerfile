FROM python:3.8-slim

RUN apt-get update && apt-get install -y ffmpeg libsndfile1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY server.py .

CMD ["python", "server.py"]
