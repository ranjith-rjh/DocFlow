"""Tests de l'API avec une base et une messagerie simulées (F-01 à F-05, T-05)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pika.exceptions import AMQPConnectionError
from sqlalchemy.exc import OperationalError

from docflow.api import app as module_app
from docflow.api.app import app

PDF = b"%PDF-1.7\n" + b"x" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 100


class FausseBase:
    def __init__(self):
        self.documents, self.echecs = {}, []
        self.panne = False

    def ping(self):
        if self.panne:
            raise OperationalError("SELECT 1", {}, Exception("down"))

    def creer_document(self, document_id, correlation_id, format_source, taille, ref):
        self.ping()
        self.documents[document_id] = {"format": format_source, "ref": ref}

    def marquer_echec(self, document_id, cause):
        self.echecs.append((document_id, cause))

    def lire(self, document_id):
        if document_id not in self.documents:
            return None
        t0 = datetime(2026, 11, 16, 15, 0, tzinfo=UTC)
        return {
            "document": {
                "document_id": document_id, "correlation_id": "RUN-1", "status": "COMPLETED",
                "erreur": None, "format_source": "pdf", "taille_octets": 109,
                "created_at": t0, "updated_at": t0, "entity": "LIDL", "date": t0.date(),
                "total_amount": Decimal("18.75"), "currency": "EUR", "confidence": {},
                "methode": {"entity": "modele"}, "champs_manquants": [], "champs_incertains": [],
                "version_modele": "v1",
            },
            "etapes": [{"event_type": "extraction.completed", "service": "ms3", "duree_ms": 4,
                        "attente_ms": None, "details": {}, "emis_le": t0 + timedelta(seconds=2)}],
        }

    def lister(self, limite):
        return []


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCFLOW_STORAGE", str(tmp_path))
    base, publies = FausseBase(), []
    etat = {"messagerie_ok": True}

    def publier(evenement):
        if not etat["messagerie_ok"]:
            raise AMQPConnectionError("down")
        publies.append(evenement)

    app.dependency_overrides[module_app.depot] = lambda: base
    app.dependency_overrides[module_app.publieur] = lambda: publier
    app.dependency_overrides[module_app.verificateur_messagerie] = lambda: (lambda: None)
    yield TestClient(app), base, publies, etat, tmp_path
    app.dependency_overrides.clear()


def test_depot_valide_202_et_evenement(client):
    c, base, publies, _, stockage = client
    r = c.post("/documents", files={"fichier": ("carrefour_2025-17-04_12.34.pdf", PDF)})
    assert r.status_code == 202
    corps = r.json()
    assert corps["status"] == "PENDING" and corps["document_id"].startswith("DOC-")
    assert publies[0].event_type == "document.received"
    # Le nom d'origine (qui contient la réponse) n'est conservé nulle part.
    ref = base.documents[corps["document_id"]]["ref"]
    assert "carrefour" not in ref and ref.endswith(".pdf")
    assert (stockage / "originaux" / f"{corps['document_id']}.pdf").read_bytes() == PDF


def test_format_reel_verifie_pas_l_extension(client):
    c, *_ = client
    r = c.post("/documents", files={"fichier": ("ticket.pdf", b"PK\x03\x04 zip deguise")})
    assert r.status_code == 415
    assert "Format non supporté" in r.json()["detail"]
    r = c.post("/documents", files={"fichier": ("photo.jpg", PNG)})
    assert r.status_code == 202  # un PNG nommé .jpg est accepté comme PNG


def test_fichier_vide_et_trop_gros(client, monkeypatch):
    c, *_ = client
    assert c.post("/documents", files={"fichier": ("v.pdf", b"")}).status_code == 400
    monkeypatch.setattr(module_app, "MAX_TAILLE_OCTETS", 50)
    assert c.post("/documents", files={"fichier": ("g.pdf", PDF)}).status_code == 413


def test_base_indisponible_503_sans_fichier_orphelin(client):
    c, base, publies, _, stockage = client
    base.panne = True
    r = c.post("/documents", files={"fichier": ("t.png", PNG)})
    assert r.status_code == 503 and publies == []
    assert not list((stockage / "originaux").glob("*"))


def test_messagerie_indisponible_503_et_document_marque_en_echec(client):
    c, base, _, etat, _ = client
    etat["messagerie_ok"] = False
    r = c.post("/documents", files={"fichier": ("t.png", PNG)})
    assert r.status_code == 503
    assert base.echecs and "Messagerie indisponible" in base.echecs[0][1]


def test_consultation_et_404(client):
    c, base, *_ = client
    base.documents["DOC-ABC"] = {}
    r = c.get("/documents/DOC-ABC")
    assert r.status_code == 200
    d = r.json()
    assert d["resultat"]["total_amount"] == "18.75"
    assert d["resultat"]["date"] == "2026-11-16"
    assert d["duree_totale_ms"] == 2000
    assert c.get("/documents/DOC-INCONNU").status_code == 404


def test_sante(client):
    c, base, *_ = client
    assert c.get("/health").json()["base"] == "ok"
    base.panne = True
    r = c.get("/health")
    assert r.status_code == 503 and r.json()["base"] == "indisponible"


def test_interface_servie(client):
    c, *_ = client
    r = c.get("/")
    assert r.status_code == 200 and "Glissez vos tickets ici" in r.text
