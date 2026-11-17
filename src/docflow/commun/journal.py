"""Journaux contextualisés par document.

Format ``clé=valeur`` sur une ligne : lisible à l'œil pendant la démonstration
et facile à filtrer (``grep document_id=DOC-...``). Le contenu des tickets n'est
jamais journalisé (cahier des charges §8.5) : seulement identifiants, étapes,
durées et causes d'erreur.
"""

from __future__ import annotations

import logging
import sys

FORMAT = "%(asctime)s %(levelname)s service=%(name)s %(message)s"


def configurer_journaux(service: str, niveau: str = "INFO") -> logging.Logger:
    """Configure la sortie standard et retourne le logger du service.

    Exemple :
        >>> log = configurer_journaux("ms2-ocr")
        >>> log.info(contexte("DOC-1", etape="ocr", duree_ms=812))  # doctest: +SKIP
        2026-11-16 ... INFO service=ms2-ocr document_id=DOC-1 etape=ocr duree_ms=812
    """
    logging.basicConfig(stream=sys.stdout, level=niveau, format=FORMAT, force=True)
    # pika est très bavard en INFO : on ne garde que ses avertissements.
    logging.getLogger("pika").setLevel(logging.WARNING)
    return logging.getLogger(service)


def contexte(document_id: str | None, **champs: object) -> str:
    """Construit un message ``document_id=... clé=valeur ...``.

    Exemple :
        >>> contexte("DOC-1", etape="ocr", pages=2)
        'document_id=DOC-1 etape=ocr pages=2'
    """
    morceaux = [f"document_id={document_id or '-'}"]
    morceaux += [f"{cle}={valeur}" for cle, valeur in champs.items()]
    return " ".join(morceaux)
