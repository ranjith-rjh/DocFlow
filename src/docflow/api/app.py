"""API d'entrée de DocFlow AI (FastAPI) et interface web minimale.

Routes (cahier des charges §9.1) :
    POST /documents                 dépôt d'un fichier -> 202 + document_id
    GET  /documents/{document_id}   statut, résultat, étapes et durées
    GET  /documents                 derniers documents (historique de l'interface)
    GET  /health                    état de l'API, de la base et de la messagerie
    GET  /                          interface glisser-déposer
    GET  /docs                      documentation interactive (Swagger)

Lancement local : ``uvicorn docflow.api.app:app --reload``
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pika.exceptions import AMQPError
from sqlalchemy.exc import SQLAlchemyError

from docflow import __version__
from docflow.commun.config import dossier_stockage, env_int
from docflow.commun.contrats import DocumentRecu, Evenement, TypeEvenement, nouvel_identifiant
from docflow.commun.formats import EXTENSIONS, detecter_format
from docflow.commun.journal import configurer_journaux, contexte
from docflow.commun.stockage import vers_reference

SERVICE = "api"
MAX_TAILLE_OCTETS = env_int("MAX_TAILLE_OCTETS", 10 * 1024 * 1024)
STATIC = Path(__file__).parent / "static"

log = configurer_journaux(SERVICE)
app = FastAPI(
    title="DocFlow AI",
    version=__version__,
    description="Dépôt de tickets de caisse et consultation de l'extraction (enseigne, date, total).",
)


# ------------------------------------------------------------------ dépendances
def depot():
    """Dépôt PostgreSQL (remplacé par un faux dans les tests)."""
    from docflow.api.depot import DepotAPI
    from docflow.commun.base import moteur

    return DepotAPI(moteur())


def publieur():
    """Fonction de publication RabbitMQ (remplacée par une fausse dans les tests)."""
    from docflow.commun.messagerie import publier_une_fois

    return publier_une_fois


def verificateur_messagerie():
    from docflow.commun.messagerie import connecter

    def verifier() -> None:
        connecter(essais=1).close()

    return verifier


Depot = Annotated[Any, Depends(depot)]


def _erreur(code: int, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


# ------------------------------------------------------------------ routes
@app.post("/documents", status_code=202, summary="Déposer un ticket (PDF, PNG ou JPEG)")
def deposer(
    fichier: Annotated[UploadFile, File(description="Ticket de caisse : PDF, PNG ou JPEG")],
    base: Depot,
    publier: Annotated[Any, Depends(publieur)],
) -> dict[str, str]:
    contenu = fichier.file.read(MAX_TAILLE_OCTETS + 1)
    if not contenu:
        raise _erreur(400, "Fichier vide")
    if len(contenu) > MAX_TAILLE_OCTETS:
        raise _erreur(413, f"Fichier trop volumineux (maximum {MAX_TAILLE_OCTETS // 1_048_576} Mo)")
    format_source = detecter_format(contenu[:16])
    if format_source is None:
        raise _erreur(415, "Format non supporté : PDF, PNG ou JPEG attendu")

    # Le nom d'origine n'est jamais conservé : il peut contenir des informations
    # personnelles (et, pour notre corpus, la réponse attendue !).
    document_id = nouvel_identifiant("DOC")
    correlation_id = nouvel_identifiant("RUN")
    racine = dossier_stockage()
    chemin = racine / "originaux" / f"{document_id}.{EXTENSIONS[format_source]}"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    reference = vers_reference(chemin, racine)

    try:
        base.creer_document(document_id, correlation_id, format_source, len(contenu), reference)
    except SQLAlchemyError as exc:
        chemin.unlink(missing_ok=True)
        log.error(contexte(document_id, evenement="base_indisponible", erreur=type(exc).__name__))
        raise _erreur(503, "Base de données momentanément indisponible, réessayez") from exc

    evenement = Evenement.creer(
        TypeEvenement.DOCUMENT_RECU, document_id, correlation_id, SERVICE,
        DocumentRecu(original_ref=reference, format_source=format_source, taille_octets=len(contenu)),
    )
    try:
        publier(evenement)
    except (AMQPError, OSError) as exc:
        log.error(contexte(document_id, evenement="messagerie_indisponible", erreur=type(exc).__name__))
        try:
            base.marquer_echec(document_id, "[api] Messagerie indisponible lors du dépôt")
        except SQLAlchemyError:
            pass
        raise _erreur(503, "Messagerie momentanément indisponible, réessayez") from exc

    log.info(contexte(document_id, evenement="depot", format=format_source, octets=len(contenu)))
    return {"document_id": document_id, "correlation_id": correlation_id, "status": "PENDING"}


def _json(valeur: Any) -> Any:
    if isinstance(valeur, Decimal):
        return str(valeur)
    if isinstance(valeur, datetime):
        return valeur.isoformat()
    if hasattr(valeur, "isoformat"):
        return valeur.isoformat()
    return valeur


def _ms(debut: datetime, fin: datetime) -> int:
    return round((fin - debut).total_seconds() * 1000)


@app.get("/documents/{document_id}", summary="Statut et résultat d'un document")
def consulter(document_id: str, base: Depot) -> dict[str, Any]:
    try:
        lu = base.lire(document_id)
    except SQLAlchemyError as exc:
        raise _erreur(503, "Base de données momentanément indisponible") from exc
    if lu is None:
        raise _erreur(404, "Document introuvable")
    d = {k: _json(v) for k, v in lu["document"].items()}
    resultat = None
    if d.get("entity") is not None:
        resultat = {k: d[k] for k in ("entity", "date", "total_amount", "currency", "confidence",
                                      "methode", "champs_manquants", "champs_incertains",
                                      "version_modele")}
    etapes = [{k: _json(v) for k, v in e.items()} for e in lu["etapes"]]
    duree = None
    fins = [e for e in lu["etapes"] if e["event_type"] == "extraction.completed"]
    if fins:
        duree = _ms(lu["document"]["created_at"], fins[0]["emis_le"])
    return {
        "document_id": d["document_id"],
        "correlation_id": d["correlation_id"],
        "status": d["status"],
        "erreur": d["erreur"],
        "format_source": d["format_source"],
        "created_at": d["created_at"],
        "updated_at": d["updated_at"],
        "resultat": resultat,
        "duree_totale_ms": duree,
        "etapes": etapes,
    }


@app.get("/documents", summary="Derniers documents déposés")
def lister(base: Depot, limite: Annotated[int, Query(ge=1, le=100)] = 20) -> list[dict[str, Any]]:
    try:
        return [{k: _json(v) for k, v in ligne.items()} for ligne in base.lister(limite)]
    except SQLAlchemyError as exc:
        raise _erreur(503, "Base de données momentanément indisponible") from exc


@app.get("/health", summary="État de l'API et de ses dépendances")
def sante(base: Depot, verifier_messagerie: Annotated[Any, Depends(verificateur_messagerie)]):
    etat = {"api": "ok", "base": "ok", "messagerie": "ok", "version": __version__}
    try:
        base.ping()
    except Exception:  # noqa: BLE001 - toute erreur = indisponible
        etat["base"] = "indisponible"
    try:
        verifier_messagerie()
    except Exception:  # noqa: BLE001
        etat["messagerie"] = "indisponible"
    code = 200 if etat["base"] == etat["messagerie"] == "ok" else 503
    return JSONResponse(etat, status_code=code)


@app.get("/", include_in_schema=False)
def accueil() -> FileResponse:
    return FileResponse(STATIC / "index.html")
