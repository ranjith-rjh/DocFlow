"""Lecture de la configuration depuis les variables d'environnement.

Aucun mot de passe, chemin ou adresse réseau n'est écrit en dur dans le code
(cahier des charges §9.3) : tout passe par l'environnement, avec des valeurs
par défaut adaptées au développement local uniquement.
"""

from __future__ import annotations

import os
from pathlib import Path


def env(nom: str, defaut: str | None = None) -> str:
    """Retourne la variable d'environnement ``nom`` ou ``defaut``.

    Lève ``RuntimeError`` si la variable est absente et sans valeur par défaut,
    pour échouer tôt et clairement plutôt qu'au milieu d'un traitement.

    Exemple :
        >>> os.environ["DOCFLOW_EXEMPLE"] = "42"
        >>> env("DOCFLOW_EXEMPLE")
        '42'
    """
    valeur = os.environ.get(nom, defaut)
    if valeur is None:
        raise RuntimeError(f"Variable d'environnement obligatoire absente : {nom}")
    return valeur


def env_int(nom: str, defaut: int) -> int:
    """Variante entière de :func:`env`."""
    return int(env(nom, str(defaut)))


def url_rabbitmq() -> str:
    """URL AMQP du bus de messages (ex. ``amqp://docflow:secret@rabbitmq:5672/``)."""
    return env("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


def url_base() -> str:
    """URL SQLAlchemy de PostgreSQL (ex. ``postgresql+psycopg://user:mdp@hote/docflow``)."""
    return env("DATABASE_URL", "postgresql+psycopg://docflow:docflow@localhost:5432/docflow")


def dossier_stockage() -> Path:
    """Racine du stockage documentaire partagé par l'API, MS1 et MS2 (côté Mac)."""
    return Path(env("DOCFLOW_STORAGE", "storage")).resolve()
