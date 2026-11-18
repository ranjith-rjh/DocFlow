"""Code partagé par les trois microservices : parler à RabbitMQ.

Principe : chaque étape a sa file. Un service lit un message dans sa file,
fait son travail, puis dépose le résultat dans la file de l'étape suivante.

    pretraitement  ->  MS1  ->  ocr  ->  MS2  ->  extraction  ->  MS3
                                                   erreurs     ->  MS3

Un message est un simple dictionnaire JSON, par exemple :
    {"document_id": "DOC-1A2B3C4D", "fichier": "originaux/DOC-1A2B3C4D.pdf",
     "durees": {"ms1": 140}}
"""

import json
import os
import time

import pika

FILES = ["pretraitement", "ocr", "extraction", "erreurs"]
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")


def ouvrir_canal():
    """Se connecte à RabbitMQ et crée les files si elles n'existent pas.

    ``durable=True`` : les files survivent à un redémarrage de RabbitMQ.
    """
    connexion = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
    canal = connexion.channel()
    for file in FILES:
        canal.queue_declare(file, durable=True)
    return canal


def publier(canal, file, message):
    """Dépose un message dans une file. ``delivery_mode=2`` : message persistant."""
    canal.basic_publish(
        exchange="",
        routing_key=file,
        body=json.dumps(message),
        properties=pika.BasicProperties(delivery_mode=2),
    )


def lancer_service(nom, abonnements):
    """Boucle principale d'un microservice.

    ``abonnements`` associe une file à une fonction ``traiter(message)`` qui
    renvoie ``(file_suivante, message_suivant)`` ou ``None`` (fin de chaîne).

    Pour chaque message :
      1. on mesure la durée du traitement et on l'ajoute dans ``durees`` ;
      2. en cas d'erreur, on envoie la cause dans la file ``erreurs`` ;
      3. on acquitte le message **après** le traitement : si le service
         s'arrête en plein milieu, RabbitMQ redonnera le message plus tard.

    Si RabbitMQ disparaît, le programme s'arrête ; Docker (Mac) ou systemd
    (Fedora) le relance automatiquement.
    """
    canal = ouvrir_canal()
    canal.basic_qos(prefetch_count=1)  # un seul message à la fois par service

    for file, traiter in abonnements.items():

        def recevoir(ch, methode, _proprietes, corps, traiter=traiter):
            message = json.loads(corps)
            debut = time.time()
            try:
                suite = traiter(message)
                if suite is not None:
                    file_suivante, message_suivant = suite
                    message_suivant.setdefault("durees", {})[nom] = round((time.time() - debut) * 1000)
                    publier(ch, file_suivante, message_suivant)
                print(f"[{nom}] {message['document_id']} traité en {time.time() - debut:.2f} s", flush=True)
            except Exception as erreur:  # le document échoue, le service continue
                print(f"[{nom}] {message['document_id']} ERREUR : {erreur}", flush=True)
                if file != "erreurs":  # jamais d'erreur sur une erreur (boucle infinie)
                    publier(ch, "erreurs", {"document_id": message["document_id"],
                                            "erreur": f"{nom} : {erreur}"})
            ch.basic_ack(methode.delivery_tag)

        canal.basic_consume(file, recevoir)

    print(f"[{nom}] prêt, en attente de messages…", flush=True)
    canal.start_consuming()


def attendre_rabbitmq(tentatives=30):
    """Au démarrage, attend que RabbitMQ réponde (utile quand tout démarre en même temps)."""
    for _ in range(tentatives):
        try:
            ouvrir_canal().connection.close()
            return
        except pika.exceptions.AMQPConnectionError:
            time.sleep(2)
    raise RuntimeError("RabbitMQ injoignable")
