"""API : point d'entrée de l'application (sur le Mac).

    POST /documents        déposer un ticket          -> 202 + document_id
    GET  /documents/{id}   statut et résultat d'un ticket
    GET  /documents        derniers tickets (pour la page web)
    GET  /health           l'API voit-elle la base et RabbitMQ ?
    GET  /                 la page web (index.html)

Lancement : uvicorn api:app --host 0.0.0.0 --port 8000
"""

import os
import uuid
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from psycopg.rows import dict_row

from commun import ouvrir_canal, publier

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://docflow:docflow@localhost:5432/docflow")
STOCKAGE = Path(os.environ.get("STOCKAGE", "storage"))
TAILLE_MAX = 10 * 1024 * 1024  # 10 Mo

app = FastAPI(title="DocFlow AI")


def base():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def format_reel(contenu):
    """Le vrai format, lu dans les premiers octets (pas dans l'extension du nom)."""
    if contenu.startswith(b"%PDF"):
        return "pdf"
    if contenu.startswith(b"\x89PNG"):
        return "png"
    if contenu.startswith(b"\xff\xd8\xff"):
        return "jpg"
    return None


@app.post("/documents", status_code=202)
def deposer(fichier: UploadFile):
    contenu = fichier.file.read()
    if not contenu:
        raise HTTPException(400, "Fichier vide")
    if len(contenu) > TAILLE_MAX:
        raise HTTPException(413, "Fichier trop volumineux (10 Mo maximum)")
    extension = format_reel(contenu)
    if extension is None:
        raise HTTPException(415, "Format non supporté : PDF, PNG ou JPEG attendu")

    # Le fichier est renommé : son nom d'origine peut contenir des infos personnelles.
    document_id = "DOC-" + uuid.uuid4().hex[:8].upper()
    chemin = STOCKAGE / "originaux" / f"{document_id}.{extension}"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)

    try:
        with base() as cx:
            cx.execute("INSERT INTO documents (document_id) VALUES (%s)", (document_id,))
        canal = ouvrir_canal()
        publier(canal, "pretraitement", {"document_id": document_id,
                                          "fichier": str(chemin.relative_to(STOCKAGE))})
        canal.connection.close()
        with base() as cx:  # PENDING = enregistré ; PROCESSING = parti dans la chaîne
            cx.execute("UPDATE documents SET status = 'PROCESSING' WHERE document_id = %s", (document_id,))
    except Exception as erreur:
        print(f"[api] {document_id} dépôt impossible : {erreur}", flush=True)
        raise HTTPException(503, "Base de données ou RabbitMQ indisponible, réessayez") from erreur
    return {"document_id": document_id, "status": "PROCESSING"}


@app.get("/documents/{document_id}")
def consulter(document_id: str):
    with base() as cx:
        document = cx.execute("SELECT * FROM documents WHERE document_id = %s", (document_id,)).fetchone()
    if document is None:
        raise HTTPException(404, "Document introuvable")
    return document


@app.get("/documents")
def lister():
    with base() as cx:
        return cx.execute("SELECT * FROM documents ORDER BY created_at DESC LIMIT 20").fetchall()


@app.get("/health")
def sante():
    etat = {"api": "ok"}
    try:
        with base() as cx:
            cx.execute("SELECT 1")
        etat["base"] = "ok"
    except Exception:
        etat["base"] = "injoignable"
    try:
        ouvrir_canal().connection.close()
        etat["rabbitmq"] = "ok"
    except Exception:
        etat["rabbitmq"] = "injoignable"
    return etat


@app.get("/")
def page_web():
    return FileResponse(Path(__file__).parent / "index.html")
