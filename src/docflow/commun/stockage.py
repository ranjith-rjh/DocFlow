"""Références de stockage ``storage://...``.

Les messages RabbitMQ ne transportent jamais les fichiers eux-mêmes, seulement
une référence (cahier des charges §4.1). Ce module convertit une référence en
chemin réel et inversement, en interdisant de sortir de la racine de stockage.

Organisation :
    storage/originaux/DOC-xxx.pdf          dépôt d'origine (renommé, API)
    storage/pretraite/DOC-xxx/page_001.png images normalisées (MS1)
"""

from __future__ import annotations

from pathlib import Path

PREFIXE = "storage://"


class ReferenceInvalide(ValueError):
    """Référence mal formée ou pointant hors du stockage."""


def vers_reference(chemin: Path, racine: Path) -> str:
    """Transforme un chemin du stockage en référence portable.

    Exemple :
        >>> vers_reference(Path("/data/originaux/DOC-1.pdf"), Path("/data"))
        'storage://originaux/DOC-1.pdf'
    """
    relatif = Path(chemin).resolve().relative_to(Path(racine).resolve())
    return PREFIXE + relatif.as_posix()


def vers_chemin(reference: str, racine: Path) -> Path:
    """Transforme une référence en chemin absolu sous ``racine``.

    Lève :class:`ReferenceInvalide` si la référence tente de sortir du stockage
    (ex. ``storage://../../etc/passwd``).

    Exemple :
        >>> vers_chemin("storage://originaux/DOC-1.pdf", Path("/data")).as_posix()
        '/data/originaux/DOC-1.pdf'
    """
    if not reference.startswith(PREFIXE):
        raise ReferenceInvalide(f"Préfixe attendu {PREFIXE!r}")
    racine = Path(racine).resolve()
    chemin = (racine / reference[len(PREFIXE):]).resolve()
    if racine != chemin and racine not in chemin.parents:
        raise ReferenceInvalide("Référence hors du stockage")
    return chemin
