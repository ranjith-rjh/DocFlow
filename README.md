# DocFlow AI

> Du ticket de caisse brut à des données fiables, grâce à trois microservices
> distribués entre un Mac (Docker) et une VM Fedora (VirtualBox).

Déposez une photo ou un PDF de ticket Carrefour, Lidl ou Intermarché :
DocFlow en extrait **l'enseigne, la date et le montant total**, puis les
enregistre dans PostgreSQL.

```
 Navigateur ──HTTP──▶ API ──▶ RabbitMQ ──▶ MS1 prétraitement ──▶ MS2 OCR ──▶ MS3 extraction ──▶ PostgreSQL
                     └───────────── Mac · Docker Desktop ─────────────┘     └── Fedora · VirtualBox ──┘
                                                               192.168.56.1  ◀── réseau privé ──▶  192.168.56.10
```

| Composant | Rôle | Où |
|---|---|---|
| **API** + interface | Dépôt (glisser-déposer), suivi, résultat | Mac, conteneur |
| **RabbitMQ** | Transporte les tâches entre les étapes | Mac, conteneur |
| **MS1** | Document → images normalisées (PDF → pages, redressement, contraste) | Mac, conteneur |
| **MS2** | OCR Tesseract français | Mac, conteneur |
| **MS3** | Extraction (modèle entraîné + règles) et écriture en base | **Fedora**, service systemd |
| **PostgreSQL** | Résultats, statuts, journal des étapes | **Fedora** |

---

## Sommaire

1. [Prérequis](#1-prérequis)
2. [Première installation](#2-première-installation-une-seule-fois)
3. [Démarrer l'application](#3-démarrer-lapplication-à-chaque-session)
4. [Utiliser l'application](#4-utiliser-lapplication)
5. [Observer le système distribué](#5-observer-le-système-distribué)
6. [Démonstration en 7 étapes](#6-démonstration-en-7-étapes)
7. [Tests](#7-tests)
8. [Entraînement, évaluation et mesures](#8-entraînement-évaluation-et-mesures)
9. [Mode de secours sans VM](#9-mode-de-secours-sans-vm)
10. [Arrêter](#10-arrêter)
11. [Dépannage](#11-dépannage)
12. [Organisation du dépôt](#12-organisation-du-dépôt)

---

## 1. Prérequis

| Élément | Version testée |
|---|---|
| Mac Apple Silicon | MacBook Pro M4 Pro, macOS 27.2 |
| Docker Desktop | 29.9.2 (Compose 5.6) |
| VirtualBox | 7.2.22 |
| VM `docflow-vm` | Fedora 45 Workstation aarch64, utilisateur `dfadmin`, IP `192.168.56.10` |
| Python (Mac, pour les tests et scripts) | 3.13, avec [`uv`](https://docs.astral.sh/uv/) |

La VM est installée et son réseau validé en suivant
[docs/installation_vm_fedora.md](docs/installation_vm_fedora.md).

---

## 2. Première installation (une seule fois)

Toutes les commandes se lancent **depuis le dossier du projet**, dans le Terminal du Mac.

### 2.1 Environnement Python du Mac

Sert aux tests, au banc de mesures et aux scripts.

```bash
uv venv .venv --python 3.13
```

```bash
uv pip install --python .venv/bin/python -e ".[dev]"
```

### 2.2 Démarrer la VM et vérifier le réseau

1. VirtualBox → `docflow-vm` → **Démarrer** (ou *Démarrage sans affichage*).
2. Attendre l'écran de connexion de Fedora (~30 s), puis :

```bash
./scripts/verifier_reseau.sh
```

Les 4 tests doivent être `[OK]`.

### 2.3 Connexion SSH par clé (recommandé)

Évite de retaper le mot de passe de `dfadmin` à chaque déploiement :

```bash
ssh-copy-id dfadmin@192.168.56.10
```

### 2.4 Générer la configuration

Crée `.env` avec des mots de passe aléatoires (ignoré par Git) :

```bash
./scripts/configurer_env.sh distribue
```

### 2.5 Lancer la partie Mac

```bash
docker compose up -d --build
```

La première construction prend quelques minutes. RabbitMQ est alors exposé sur
`192.168.56.1:5672` pour que MS3 puisse s'y connecter depuis la VM.

### 2.6 Modèle d'extraction

Le modèle est construit à partir de vos tickets privés : il n'est pas dans Git.
S'il n'existe pas encore (`models/docflow-extraction.joblib`) :

```bash
docker compose --profile outils run --rm outils python -m training.corpus
```

```bash
docker compose --profile outils run --rm outils python -m training.ocr_corpus
```

```bash
docker compose --profile outils run --rm outils python -m training.entrainement
```

Sans modèle, MS3 fonctionne quand même avec la baseline par règles.

### 2.7 Déployer le nœud B (PostgreSQL + MS3) sur Fedora

```bash
./scripts/deployer_noeud_b.sh
```

Le script copie le code, le schéma et le modèle dans la VM, puis lance
l'installation. **Le mot de passe `sudo` de `dfadmin` vous est demandé.** Il
installe PostgreSQL, crée la base et les comptes, crée le service
`docflow-ms3`, puis vérifie qu'il joint RabbitMQ.
Fin attendue :

```
  [OK]    RabbitMQ joignable sur 192.168.56.1:5672
  [OK]    PostgreSQL actif
  [OK]    docflow-ms3 actif
```

À relancer après chaque modification du code de MS3 ou du modèle.

---

## 3. Démarrer l'application (à chaque session)

L'ordre compte : RabbitMQ s'expose sur l'adresse du réseau privé, qui n'existe
que lorsque la VM tourne.

1. **VM** : VirtualBox → `docflow-vm` → **Démarrer**. PostgreSQL et MS3
   démarrent tout seuls avec Fedora.
2. **Docker Desktop** : l'ouvrir et attendre « Engine running ».
3. **Application** :

```bash
docker compose up -d
```

4. **Vérification complète** (réseau + RabbitMQ + PostgreSQL + API) :

```bash
./scripts/verifier_reseau.sh --services
```

Si MS3 a démarré avant RabbitMQ, il réessaie tout seul toutes les quelques secondes.

---

## 4. Utiliser l'application

### Interface web

Ouvrir **<http://localhost:8000>** :

- glisser un ou plusieurs tickets (PDF, PNG, JPEG, 10 Mo max) dans le rectangle,
  ou cliquer dessus pour les choisir ;
- chaque ticket affiche son avancement (Reçu → MS1 → MS2 → MS3) avec la durée
  de chaque étape, puis l'enseigne, la date et le total ;
- la puce `modèle` ou `règles` indique la méthode réellement utilisée pour
  chaque champ, et `incertain` signale une confiance faible ;
- les pastilles en haut à droite indiquent l'état de l'API, de PostgreSQL et
  de RabbitMQ.

### En ligne de commande

Déposer un ticket :

```bash
curl -s -F "fichier=@data/raw/lidl/<fichier>.png" http://localhost:8000/documents
```

Réponse `202` : `{"document_id": "DOC-…", "status": "PENDING", …}`

Consulter le statut et le résultat :

```bash
curl -s http://localhost:8000/documents/DOC-XXXXXXXXXXXX | python3 -m json.tool
```

Derniers documents, et état des dépendances :

```bash
curl -s "http://localhost:8000/documents?limite=5" | python3 -m json.tool
```

```bash
curl -s http://localhost:8000/health
```

Documentation interactive de l'API (Swagger) : <http://localhost:8000/docs>.

| Code | Signification |
|---|---|
| 202 | Document accepté, traitement lancé |
| 400 / 413 / 415 | Fichier vide / trop gros / format non supporté (le contenu réel est vérifié, pas l'extension) |
| 404 | Identifiant inconnu |
| 503 | Base ou messagerie momentanément indisponible |

---

## 5. Observer le système distribué

| Quoi | Commande / adresse |
|---|---|
| Files RabbitMQ (messages en attente, débit) | <http://localhost:15672>, utilisateur `docflow`, mot de passe : `RABBITMQ_PASSWORD` dans `.env` |
| Journaux MS1 / MS2 / API (Mac) | `docker compose logs -f ms1 ms2 api` |
| Journaux MS3 (Fedora) | `ssh -t dfadmin@192.168.56.10 sudo journalctl -u docflow-ms3 -f` |
| État du service MS3 | `ssh -t dfadmin@192.168.56.10 systemctl status docflow-ms3` |
| Contenu de PostgreSQL | voir ci-dessous |
| Images préparées par MS1 | `storage/pretraite/DOC-…/page_001.png` |

Derniers résultats en base, depuis le Mac :

```bash
ssh -t dfadmin@192.168.56.10 "sudo -u postgres psql docflow -c \"SELECT d.document_id, d.status, r.entity, r.date, r.total_amount FROM documents d LEFT JOIN resultats r USING (document_id) ORDER BY d.created_at DESC LIMIT 10;\""
```

Chaque ligne de journal contient `document_id=DOC-…` : un `grep` suffit pour
suivre un document d'un bout à l'autre, du Mac à Fedora.

---

## 6. Démonstration en 7 étapes

Le déroulé du §12 du cahier des charges.

| # | Montrer | Comment |
|---|---|---|
| 1 | Dépôt | Glisser 3 tickets (une enseigne chacun) dans <http://localhost:8000> |
| 2 | Les files | Console RabbitMQ → *Queues* : `docflow.ms1…`, `docflow.ms2.ocr`, `docflow.ms3…` |
| 3 | MS1 / MS2 au travail | `docker compose logs -f ms1 ms2` |
| 4 | MS3 sur Fedora | `ssh -t dfadmin@192.168.56.10 sudo journalctl -u docflow-ms3 -f` |
| 5 | PostgreSQL | requête du §5 |
| 6 | Panne puis reprise | voir ci-dessous |
| 7 | Métriques | durées dans l'interface, `reports/rapport_mesures.md` |

**Panne de MS2 (T-07)** :

```bash
docker compose stop ms2
```

Déposer un ticket : il reste « En attente » et un message apparaît dans la file
`docflow.ms2.ocr`. Puis relancer MS2 :

```bash
docker compose start ms2
```

Le ticket se termine sans rien perdre.

**Panne du nœud B (MS3 sur Fedora)** :

```bash
ssh -t dfadmin@192.168.56.10 sudo systemctl stop docflow-ms3
```

MS1 et MS2 continuent ; les résultats attendent dans `docflow.ms3.extraction`.

```bash
ssh -t dfadmin@192.168.56.10 sudo systemctl start docflow-ms3
```

**Montée en charge** : ajouter deux lecteurs OCR, sans changer le code.

```bash
docker compose up -d --scale ms2=3
```

---

## 7. Tests

| Commande | Ce qui est testé | Prérequis |
|---|---|---|
| `.venv/bin/python -m pytest` | 94 tests unitaires et doctests (normalisation, candidats, prétraitement, contrats, logique de tentatives, API simulée) | aucun |
| `.venv/bin/python -m pytest -m integration -v` | Acceptation T-01 à T-09 sur tickets **synthétiques** : formats, inclinaison, multipage, refus, total ambigu, panne de MS2, doublons, consultation | application lancée |
| `PYTHONPATH=src:. .venv/bin/python scripts/acceptation_reelle.py` | T-01 à T-04 sur **vos vrais tickets** (partition validation), affiche seulement OK / ÉCHEC | application lancée |
| `./scripts/verifier_reseau.sh --services` | T-10 : réseau privé, ports RabbitMQ et PostgreSQL, API | VM + application |
| `.venv/bin/ruff check src tests training scripts` | style et erreurs courantes | aucun |

Les tests versionnés n'utilisent **aucun ticket réel** (tickets dessinés avec Pillow/PyMuPDF).

---

## 8. Entraînement, évaluation et mesures

Tout se lance dans l'image `outils`, qui contient Tesseract français et ne dispose d'aucun réseau.
Préfixe commun : `docker compose --profile outils run --rm outils`.

| Étape | Commande (après le préfixe) | Produit |
|---|---|---|
| Annotations + découpage figé | `python -m training.corpus` | `data/annotations/` (privé) |
| OCR du corpus (MS1 + MS2) | `python -m training.ocr_corpus` | `data/interim/` (privé) |
| Baseline sur train + validation | `python -m training.evaluation` | `reports/baseline_dev.md` |
| Entraînement + validation croisée | `python -m training.entrainement` | `models/` (privé), [docs/modele.md](docs/modele.md) |
| Bilan sur le test (**une seule fois**) | `python -m training.evaluation --final` | [reports/evaluation_finale.md](reports/evaluation_finale.md) |
| Pipeline monolithique (référence) | `python scripts/pipeline_locale.py --resume <fichiers>` | latence d'un seul processus |

Mesures de performance (sur le Mac, application lancée) :

```bash
.venv/bin/python scripts/benchmark.py --nombre 20 --sequentiel --libelle distribue-sequentiel
```

```bash
.venv/bin/python scripts/benchmark.py --nombre 60 --libelle distribue-charge
```

Mesure d'énergie (demande le mot de passe administrateur du Mac pour `powermetrics`) :

```bash
./scripts/mesurer_energie.sh
```

Résultats et protocole : [reports/rapport_mesures.md](reports/rapport_mesures.md).

---

## 9. Mode de secours sans VM

Si la VM ne démarre pas le jour J, MS3 et PostgreSQL peuvent tourner en
conteneurs sur le Mac. C'est le même code, mais ce n'est **pas** la cible distribuée.

```bash
./scripts/configurer_env.sh local
```

```bash
docker compose up -d --build
```

Retour au mode distribué : arrêter d'abord le MS3 et le PostgreSQL locaux,
sinon ils continueraient à consommer les messages.

```bash
docker compose --profile noeud-b-local down
```

```bash
./scripts/configurer_env.sh distribue && docker compose up -d
```

Les mots de passe sont conservés d'un mode à l'autre. Les données des deux
modes sont séparées : conteneur PostgreSQL d'un côté, PostgreSQL de Fedora de l'autre.

---

## 10. Arrêter

```bash
docker compose down
```

Puis éteindre la VM depuis VirtualBox (*Fermer → Envoyer le signal d'extinction*).
`docker compose down -v` supprime en plus les volumes (files RabbitMQ et base
du mode local) : à éviter sauf pour repartir de zéro.

---

## 11. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `docker compose up` : *cannot assign requested address 192.168.56.1* | La VM n'est pas démarrée, donc l'adresse privée du Mac n'existe pas | Démarrer la VM, puis relancer `docker compose up -d` |
| Pastille PostgreSQL rouge, `/health` → 503 | VM éteinte, ou PostgreSQL arrêté | `./scripts/verifier_reseau.sh --services` ; `ssh -t dfadmin@192.168.56.10 systemctl status postgresql` |
| Documents bloqués « En cours » à l'étape Extraction | MS3 arrêté ou sans accès à RabbitMQ | `ssh -t dfadmin@192.168.56.10 sudo journalctl -u docflow-ms3 -n 50` |
| MS3 : `rabbitmq_indisponible` en boucle | `.env` en mode `local` (RabbitMQ limité à 127.0.0.1), ou pare-feu macOS | `./scripts/configurer_env.sh distribue && docker compose up -d` ; autoriser Docker dans Réglages → Réseau → Coupe-feu |
| `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!` | VM réinstallée à la même adresse | voir la section Dépannage de [docs/installation_vm_fedora.md](docs/installation_vm_fedora.md) |
| Messages dans `docflow.erreurs` | Tentatives épuisées pendant une panne longue | Corriger la cause, puis `.venv/bin/python scripts/rejouer_erreurs.py --rejouer` |
| Statut `FAILED` « PDF illisible ou corrompu » | Fichier réellement abîmé | Comportement attendu, rien n'est inventé |

---

## 12. Organisation du dépôt

```
src/docflow/
  commun/         contrats de messages, RabbitMQ, stockage, configuration, journaux
  pretraitement/  MS1 : traitement.py (cœur métier) + service.py (worker)
  ocr/            MS2 : moteur.py + service.py
  extraction/     MS3 : candidats, règles, modèle, extracteur, dépôt SQL, schema.sql, service.py
  api/            API FastAPI + static/index.html (interface)
training/         annotations, découpage, OCR du corpus, entraînement, évaluation
scripts/          configuration, déploiement, réseau, mesures, acceptation, rejeu
deploy/           installation Fedora (systemd) et comptes PostgreSQL
docker/           Dockerfile multi-cibles (api, ms1, ms2, ms3, outils)
tests/            tests unitaires + tests/integration (acceptation T-01 à T-09)
docs/             cahier des charges suivi : backlog, décisions, contrats, corpus, modèle, VM, journal des tests
reports/          évaluations et mesures (agrégats uniquement)
data/ storage/ models/   données privées, ignorées par Git
```

Documents de référence :

| Document | Contenu |
|---|---|
| [cahier_des_charges.md](cahier_des_charges.md) | Besoin initial |
| [docs/decisions.md](docs/decisions.md) | Toutes les décisions D-01 à D-10 et leur justification |
| [docs/contrats.md](docs/contrats.md) | Messages, files RabbitMQ, statuts |
| [docs/modele.md](docs/modele.md) | Ce qui est appris, ce qui reste déterministe, validation croisée |
| [docs/corpus.md](docs/corpus.md) | Corpus, découpage, limites |
| [docs/journal_tests.md](docs/journal_tests.md) | Résultats réellement observés des tests d'acceptation |
| [docs/backlog.md](docs/backlog.md) | Avancement ticket par ticket |

**Confidentialité** : les tickets, annotations, caches OCR, modèles et `.env`
ne sont jamais committés (`.gitignore`) ; les journaux ne contiennent ni texte
de ticket ni nom de fichier d'origine.
