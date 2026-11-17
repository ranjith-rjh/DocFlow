"""DocFlow AI : du ticket de caisse brut à des données fiables.

Sous-paquets :
    commun        : contrats de messages, messagerie RabbitMQ, stockage, journaux.
    pretraitement : cœur de MS1 (document -> images normalisées).
    ocr           : cœur de MS2 (images -> texte et lignes).
    extraction    : cœur de MS3 (texte -> entité, date, total ; insertion SQL).
    api           : point d'entrée HTTP et interface web minimale.
"""

__version__ = "1.0.0"
