# Contrats de messages — version `v1`

Source de vérité : [`src/docflow/commun/contrats.py`](../src/docflow/commun/contrats.py)
(modèles Pydantic stricts : un champ inconnu ou une version différente est refusé).

## Enveloppe commune

| Champ | Rôle |
|---|---|
| `event_id` | Identifiant unique de l'événement (clé d'idempotence du journal) |
| `event_type` | Type = clé de routage RabbitMQ |
| `version` | `v1` |
| `document_id` | `DOC-XXXXXXXXXXXX`, stable sur toute la chaîne |
| `correlation_id` | `RUN-XXXXXXXXXXXX`, constant pour un dépôt |
| `created_at` | Horodatage UTC d'émission |
| `service` | Émetteur (`api`, `ms1-pretraitement`, `ms2-ocr`, `ms3-extraction`) |
| `payload` | Charge utile propre au type |

## Événements

| `event_type` | Émis par | Consommé par | Charge utile |
|---|---|---|---|
| `document.received` | API | MS1 | `original_ref`, `format_source`, `taille_octets` |
| `step.started` | MS1, MS2, MS3 | journal MS3 | `etape`, `attente_ms` (temps en file) |
| `preprocessing.completed` | MS1 | MS2 | `pages_refs[]`, `nb_pages`, `format_source`, `duree_ms`, `angles[]` |
| `ocr.completed` | MS2 | MS3 | `pages[]` (lignes : `texte`, `y_rel`, `confiance`), `pages_vides[]`, `duree_ms`, `moteur` |
| `extraction.completed` | MS3 | journal MS3 | champs extraits, `methode`, `confidence`, `version_modele`, `duree_ms` |
| `processing.failed` | tout worker | journal MS3 | `etape`, `cause`, `definitif`, `tentatives` |

`step.started` s'ajoute aux cinq événements du cahier des charges : il fait
passer le document à `PROCESSING` et mesure le temps d'attente en file (§11.2).

## Ce qui voyage et ce qui ne voyage pas

- **Jamais** de PDF ni d'image dans un message : seulement des références
  `storage://originaux/DOC-….pdf`, `storage://pretraite/DOC-…/page_001.png`.
- **Le texte OCR voyage dans `ocr.completed`** (quelques Ko) : MS3, sur
  Fedora, n'a pas accès au stockage du Mac. C'est le principe du §5.2 : on
  envoie au bureau la transcription, pas le carton.
- Le journal en base ne garde que des métadonnées (pages, durées, causes),
  jamais le texte du ticket.

## Topologie RabbitMQ

| Élément | Type | Liaison |
|---|---|---|
| `docflow.events` | exchange topic, durable | — |
| `docflow.ms1.pretraitement` | file durable | `document.received` |
| `docflow.ms2.ocr` | file durable | `preprocessing.completed` |
| `docflow.ms3.extraction` | file durable | `ocr.completed` |
| `docflow.ms3.journal` | file durable | `#` (tous) |
| `docflow.dlx` → `docflow.erreurs` | exchange fanout + file | messages abandonnés |

Fiabilité : messages persistants, confirmations de publication, `prefetch=1`,
acquittement après succès, 3 tentatives (délai 2 s puis 4 s) puis file
d'erreur ; erreur définitive (fichier corrompu) → `processing.failed` immédiat.

## Statuts

| Événement reçu par le journal | Statut du document |
|---|---|
| (dépôt, écrit par l'API) | `PENDING` |
| `step.started` | `PROCESSING` |
| résultat écrit par MS3 | `COMPLETED` (même transaction que le résultat) |
| `processing.failed` | `FAILED` + cause |

Un statut terminal n'est jamais rétrogradé (relivraisons, messages en retard).
