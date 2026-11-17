# Images DocFlow AI : une cible par composant (docker build --target <cible>).
#
#   api    : point d'entrée HTTP + interface web           (Mac)
#   ms1    : prétraitement documentaire                     (Mac)
#   ms2    : OCR Tesseract français                         (Mac)
#   ms3    : extraction + insertion (mode « nœud B local »  ; en cible, MS3 tourne sur Fedora)
#   outils : entraînement, évaluation et tests hors ligne

FROM python:3.12.8-slim-bookworm AS socle
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN useradd --create-home --uid 1000 docflow
COPY pyproject.toml ./
COPY src ./src

# ---------------------------------------------------------------- API
FROM socle AS api
RUN pip install ".[api]"
USER docflow
EXPOSE 8000
CMD ["uvicorn", "docflow.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------- MS1
FROM socle AS ms1
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
RUN pip install ".[ms1]"
USER docflow
CMD ["python", "-m", "docflow.pretraitement.service"]

# ---------------------------------------------------------------- MS2
FROM socle AS ms2
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra \
 && rm -rf /var/lib/apt/lists/*
RUN pip install ".[ms2]"
# Un seul thread par Tesseract : on parallélise en lançant plusieurs workers.
ENV OMP_THREAD_LIMIT=1
USER docflow
CMD ["python", "-m", "docflow.ocr.service"]

# ---------------------------------------------------------------- MS3
FROM socle AS ms3
RUN pip install ".[ms3]"
USER docflow
CMD ["python", "-m", "docflow.extraction.service"]

# ---------------------------------------------------------------- Outils
FROM ms2 AS outils
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
RUN pip install ".[dev]"
COPY training ./training
COPY tests ./tests
COPY scripts ./scripts
USER docflow
CMD ["python", "-m", "pytest", "-q"]
