"""Rejoue les messages de la file d'erreur ``docflow.erreurs``.

Après une panne prolongée (ex. VM Fedora éteinte trop longtemps), des messages
peuvent avoir épuisé leurs tentatives. Une fois la cause corrigée, ce script
les renvoie dans leur file d'origine (lue dans l'en-tête ``x-death``).

    .venv/bin/python scripts/rejouer_erreurs.py            # affiche seulement
    .venv/bin/python scripts/rejouer_erreurs.py --rejouer  # renvoie les messages
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import pika

from docflow.commun.messagerie import FILE_ERREURS, declarer_topologie


def url_depuis_env() -> str:
    env = dict(l.split("=", 1) for l in Path(".env").read_text().splitlines()  # noqa: E741
               if "=" in l and not l.startswith("#"))
    hote = env.get("RABBITMQ_BIND_IP", "127.0.0.1")
    return os.environ.get("RABBITMQ_URL",
                          f"amqp://{env['RABBITMQ_USER']}:{env['RABBITMQ_PASSWORD']}@{hote}:5672/")


def main() -> None:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--rejouer", action="store_true")
    args = parseur.parse_args()

    connexion = pika.BlockingConnection(pika.URLParameters(url_depuis_env()))
    canal = connexion.channel()
    canal.confirm_delivery()
    declarer_topologie(canal)
    n = 0
    while True:
        methode, proprietes, corps = canal.basic_get(FILE_ERREURS, auto_ack=False)
        if methode is None:
            break
        morts = (proprietes.headers or {}).get("x-death") or [{}]
        origine = morts[0].get("queue", "?")
        n += 1
        print(f"{n:3d}. type={proprietes.type} file_origine={origine}")
        if args.rejouer and origine != "?":
            entetes = {k: v for k, v in (proprietes.headers or {}).items() if k != "x-death"}
            entetes.pop("x-docflow-tentative", None)
            proprietes.headers = entetes
            canal.basic_publish("", origine, corps, proprietes, mandatory=True)
            canal.basic_ack(methode.delivery_tag)
        # En lecture seule, les messages restent non acquittés : RabbitMQ les
        # remet dans la file à la fermeture de la connexion.
    connexion.close()
    print(f"{n} message(s) {'rejoué(s)' if args.rejouer else 'en erreur (lecture seule)'}.")


if __name__ == "__main__":
    main()
