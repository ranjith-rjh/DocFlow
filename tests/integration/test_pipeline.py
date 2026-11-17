"""Tests d'acceptation de bout en bout sur l'application lancée (§12).

Nécessitent la pile démarrée (mode local ou distribué) :
    docker compose up -d
    .venv/bin/python -m pytest -m integration -v

Couvre T-01 à T-09 sur des tickets **synthétiques** (les tickets réels sont
vérifiés par ``scripts/acceptation_reelle.py``, qui n'affiche que OK/ÉCHEC).
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

import httpx
import pika
import pytest
from sqlalchemy import create_engine, text

from docflow.commun.contrats import (
    Evenement,
    LigneMessage,
    OcrTermine,
    PageMessage,
    TypeEvenement,
)
from docflow.commun.messagerie import declarer_topologie, publier
from tests.integration.fabrique import TICKET_AMBIGU, TICKET_CARREFOUR, image_ticket, pdf_ticket

pytestmark = pytest.mark.integration
API = os.environ.get("DOCFLOW_API", "http://localhost:8000")
RACINE = Path(__file__).resolve().parents[2]


def lire_env() -> dict[str, str]:
    env = {}
    for ligne in (RACINE / ".env").read_text().splitlines():
        if "=" in ligne and not ligne.startswith("#"):
            cle, valeur = ligne.split("=", 1)
            env[cle] = valeur
    return env


ENV = lire_env()


def url_base_hote() -> str:
    """URL de la base vue depuis le Mac (compte docflow_api, lecture seule)."""
    return ENV["API_DATABASE_URL"].replace("@postgres:5432", "@localhost:5433")


def url_rabbitmq_hote() -> str:
    hote = ENV.get("RABBITMQ_BIND_IP", "127.0.0.1")
    return f"amqp://{ENV['RABBITMQ_USER']}:{ENV['RABBITMQ_PASSWORD']}@{hote}:5672/"


def deposer(contenu: bytes, nom: str) -> str:
    r = httpx.post(f"{API}/documents", files={"fichier": (nom, contenu)}, timeout=10)
    assert r.status_code == 202, r.text
    return r.json()["document_id"]


def attendre(document_id: str, delai: float = 60) -> dict:
    fin = time.time() + delai
    while time.time() < fin:
        d = httpx.get(f"{API}/documents/{document_id}", timeout=5).json()
        if d["status"] in ("COMPLETED", "FAILED"):
            return d
        time.sleep(0.5)
    raise AssertionError(f"{document_id} toujours en cours après {delai} s")


def messages_en_file(file: str, attendu: int = 1, delai: float = 15) -> int:
    """Nombre de messages en file (les statistiques RabbitMQ sont rafraîchies toutes les 5 s)."""
    fin = time.time() + delai
    while True:
        n = _messages_en_file(file)
        if n >= attendu or time.time() > fin:
            return n
        time.sleep(1)


def _messages_en_file(file: str) -> int:
    requete = urllib.request.Request(f"http://localhost:15672/api/queues/%2F/{file}")
    jeton = base64.b64encode(f"{ENV['RABBITMQ_USER']}:{ENV['RABBITMQ_PASSWORD']}".encode()).decode()
    requete.add_header("Authorization", f"Basic {jeton}")
    with urllib.request.urlopen(requete, timeout=5) as r:
        return json.load(r)["messages"]


@pytest.fixture(scope="module", autouse=True)
def pile_disponible():
    try:
        sante = httpx.get(f"{API}/health", timeout=5)
    except httpx.HTTPError:
        pytest.skip("API non lancée (docker compose up -d)")
    if sante.status_code != 200:
        pytest.skip(f"Pile incomplète : {sante.text}")


# ------------------------------------------------------------------ T-01 à T-06
def test_t01_jpeg_lisible_extrait_et_persiste():
    d = attendre(deposer(image_ticket(TICKET_CARREFOUR, format_="JPEG"), "ticket.jpg"))
    assert d["status"] == "COMPLETED"
    r = d["resultat"]
    assert (r["entity"], r["date"], r["total_amount"], r["currency"]) == \
        ("CARREFOUR", "2026-11-05", "4.54", "EUR")


def test_t02_png_incline_redresse_puis_extrait():
    d = attendre(deposer(image_ticket(TICKET_CARREFOUR, angle=7), "incline.png"))
    angles = [e["details"].get("angles") for e in d["etapes"]
              if e["event_type"] == "preprocessing.completed"][0]
    assert abs(angles[0] + 7) <= 1.0, angles  # MS1 a compensé l'inclinaison
    assert d["resultat"]["total_amount"] == "4.54"


def test_t03_t04_pdf_multipage():
    pages = [TICKET_CARREFOUR[:5], TICKET_CARREFOUR[5:]]
    d = attendre(deposer(pdf_ticket(pages), "multi.pdf"))
    pre = [e for e in d["etapes"] if e["event_type"] == "preprocessing.completed"][0]
    assert pre["details"]["nb_pages"] == 2
    assert d["resultat"]["total_amount"] == "4.54"
    assert d["resultat"]["date"] == "2026-11-05"


def test_t05_format_non_supporte_refuse_sans_plantage():
    r = httpx.post(f"{API}/documents", files={"fichier": ("x.pdf", b"GIF89a fausse image")})
    assert r.status_code == 415
    assert httpx.get(f"{API}/health").status_code == 200


def test_t05_pdf_corrompu_echec_explicite():
    d = attendre(deposer(b"%PDF-1.7\n tronque", "corrompu.pdf"))
    assert d["status"] == "FAILED"
    assert "PDF illisible" in d["erreur"]


def test_t06_total_ambigu_bon_candidat():
    d = attendre(deposer(image_ticket(TICKET_AMBIGU), "ambigu.png"))
    assert d["resultat"]["total_amount"] == "3.02"


# ------------------------------------------------------------------ T-07 panne
def test_t07_arret_de_ms2_puis_reprise():
    subprocess.run(["docker", "compose", "stop", "ms2"], cwd=RACINE, check=True, capture_output=True)
    try:
        document_id = deposer(image_ticket(TICKET_CARREFOUR), "panne.png")
        time.sleep(4)
        d = httpx.get(f"{API}/documents/{document_id}").json()
        assert d["status"] in ("PENDING", "PROCESSING")
        assert messages_en_file("docflow.ms2.ocr") >= 1  # tâche conservée par RabbitMQ
    finally:
        subprocess.run(["docker", "compose", "start", "ms2"], cwd=RACINE, check=True,
                       capture_output=True)
    assert attendre(document_id)["status"] == "COMPLETED"


# ------------------------------------------------------------------ T-08 doublons
def test_t08_evenement_republie_aucun_doublon():
    document_id = deposer(image_ticket(TICKET_CARREFOUR), "doublon.png")
    d = attendre(document_id)
    evenement = Evenement.creer(
        TypeEvenement.OCR_TERMINE, document_id, d["correlation_id"], "test-t08",
        OcrTermine(pages=[PageMessage(numero=1, nb_mots=3, confiance_moyenne=90, lignes=[
            LigneMessage(texte=t, y_rel=i / 10, confiance=90) for i, t in enumerate(TICKET_CARREFOUR)
        ])], duree_ms=1, moteur="test"),
    )
    connexion = pika.BlockingConnection(pika.URLParameters(url_rabbitmq_hote()))
    canal = connexion.channel()
    canal.confirm_delivery()
    declarer_topologie(canal)
    publier(canal, evenement)
    publier(canal, evenement)  # même event_id, relivré
    connexion.close()
    time.sleep(4)

    with create_engine(url_base_hote()).connect() as cx:
        resultats = cx.execute(text("SELECT count(*) FROM resultats WHERE document_id = :d"),
                               {"d": document_id}).scalar()
        journal = cx.execute(text("SELECT count(*) FROM journal_etapes WHERE event_id = :e"),
                             {"e": evenement.event_id}).scalar()
    assert resultats == 1
    assert journal == 1


# ------------------------------------------------------------------ T-09 consultation
def test_t09_resultat_coherent_et_trace():
    document_id = deposer(image_ticket(TICKET_CARREFOUR), "trace.png")
    d = attendre(document_id)
    types = [e["event_type"] for e in d["etapes"]]
    for attendu in ("document.received", "preprocessing.completed", "ocr.completed",
                    "extraction.completed"):
        assert attendu in types
    assert types.count("step.started") == 3
    assert d["duree_totale_ms"] > 0
    assert httpx.get(f"{API}/documents/DOC-INEXISTANT").status_code == 404
