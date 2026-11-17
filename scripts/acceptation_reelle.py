"""Tests d'acceptation T-01 à T-04 sur de **vrais** tickets (données privées, locales).

Utilise des tickets de la partition *validation* (jamais ceux du test) et
n'affiche que OK / ÉCHEC, sans aucune valeur de ticket.

    .venv/bin/python scripts/acceptation_reelle.py
"""

from __future__ import annotations

import io
import time
from pathlib import Path

import httpx
import pymupdf
from PIL import Image

from training.corpus import charger_annotations

API = "http://localhost:8000"


def attendre(document_id: str) -> dict:
    for _ in range(240):
        d = httpx.get(f"{API}/documents/{document_id}").json()
        if d["status"] == "FAILED" or (d["status"] == "COMPLETED" and d["duree_totale_ms"]):
            return d
        time.sleep(0.5)
    raise TimeoutError(document_id)


def verifier(nom: str, contenu: bytes, attendu: dict) -> bool:
    r = httpx.post(f"{API}/documents", files={"fichier": ("ticket", contenu)}, timeout=30)
    r.raise_for_status()
    d = attendre(r.json()["document_id"])
    res = d["resultat"] or {}
    ok = d["status"] == "COMPLETED" and all(res.get(k) == attendu[k]
                                            for k in ("entity", "date", "total_amount"))
    champs_faux = [k for k in ("entity", "date", "total_amount") if res.get(k) != attendu[k]]
    print(f"  [{'OK' if ok else 'ÉCHEC'}] {nom}" + (f" — champs faux : {champs_faux}" if not ok else ""))
    return ok


def main() -> None:
    val = [a for a in charger_annotations() if a["partition"] == "validation"]
    choisir = lambda e: next(a for a in val if a["entity"] == e)  # noqa: E731
    carrefour, lidl, inter = choisir("CARREFOUR"), choisir("LIDL"), choisir("INTERMARCHE")
    deux_pages = next((a for a in val if a["entity"] == "CARREFOUR"
                       and pymupdf.open(Path("data/raw", a["fichier"])).page_count == 2), None)

    print("Acceptation sur tickets réels (partition validation) :")
    resultats = []

    # T-01 : JPEG — page Carrefour convertie en photo JPEG
    page = pymupdf.open(Path("data/raw", carrefour["fichier"]))[0].get_pixmap(dpi=150)
    jpeg = io.BytesIO()
    Image.frombytes("RGB", (page.width, page.height), page.samples).save(jpeg, "JPEG", quality=85)
    resultats.append(verifier("T-01 JPEG Carrefour", jpeg.getvalue(), carrefour))

    # T-02 : PNG Lidl incliné de 6°
    image = Image.open(Path("data/raw", lidl["fichier"])).convert("RGB")
    incline = io.BytesIO()
    image.rotate(6, expand=True, fillcolor="white", resample=Image.BICUBIC).save(incline, "PNG")
    resultats.append(verifier("T-02 PNG Lidl incliné de 6°", incline.getvalue(), lidl))

    # T-03 : PDF Intermarché
    resultats.append(verifier("T-03 PDF Intermarché", Path("data/raw", inter["fichier"]).read_bytes(), inter))

    # T-04 : PDF de plusieurs pages
    if deux_pages:
        resultats.append(verifier("T-04 PDF Carrefour 2 pages",
                                  Path("data/raw", deux_pages["fichier"]).read_bytes(), deux_pages))
    print(f"{sum(resultats)}/{len(resultats)} réussis")


if __name__ == "__main__":
    main()
