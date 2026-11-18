# Une seule image pour tout le côté Mac : API, MS1, MS2 et outils.
# Chaque conteneur lance un programme différent (voir docker-compose.yml).
FROM python:3.12-slim

# Tesseract + la langue française pour l'OCR (MS2)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py index.html ./

# Un seul cœur par OCR : on parallélise en lançant plusieurs conteneurs MS2.
ENV OMP_THREAD_LIMIT=1 PYTHONUNBUFFERED=1
