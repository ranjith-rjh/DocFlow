"""Détection du format réel d'un fichier (partagée par l'API et MS1).

On se fie aux premiers octets (« octets magiques »), jamais à l'extension :
un ``.zip`` renommé en ``.pdf`` doit être refusé (cahier des charges §7.1).
"""

from __future__ import annotations

EXTENSIONS = {"pdf": "pdf", "png": "png", "jpeg": "jpg"}


def detecter_format(debut: bytes) -> str | None:
    """Identifie le format réel à partir des premiers octets du fichier.

    Exemple :
        >>> detecter_format(b"%PDF-1.7 ...")
        'pdf'
        >>> detecter_format(b"\\x89PNG\\r\\n\\x1a\\n...")
        'png'
        >>> detecter_format(b"\\xff\\xd8\\xff\\xe0...")
        'jpeg'
        >>> detecter_format(b"GIF89a") is None
        True
    """
    if debut.startswith(b"%PDF-"):
        return "pdf"
    if debut.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if debut.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None
