"""Connexion PostgreSQL partagée par l'API et MS3 (SQLAlchemy Core, sans ORM).

Les requêtes sont écrites en SQL explicite (``text``) : plus lisibles pour
expliquer l'idempotence (``ON CONFLICT``) qu'une couche ORM.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from docflow.commun.config import url_base


@lru_cache(maxsize=1)
def moteur() -> Engine:
    """Moteur SQLAlchemy unique par processus.

    ``pool_pre_ping`` vérifie chaque connexion avant usage : après un
    redémarrage de la VM Fedora, les connexions mortes sont remplacées au lieu
    de provoquer une erreur.
    """
    return create_engine(
        url_base(),
        pool_pre_ping=True,
        pool_size=5,
        connect_args={"connect_timeout": 5, "application_name": "docflow"},
    )
