# DocFlow AI — V2 (version simple)

Déposez un ticket de caisse (PDF, PNG ou JPEG) : DocFlow lit le texte et
enregistre **l'enseigne, la date et le total** dans une base PostgreSQL.

> La V1, plus complète, reste disponible sur la branche `main`.
> La V2 vise le même cahier des charges avec un code qu'on peut lire et
> expliquer en entier.

## Comment ça marche

```
                         MAC (Docker)                                 VM FEDORA (192.168.56.10)
 ┌─────────┐   ┌─────┐   ┌──────────────── RabbitMQ ─────────────────┐   ┌─────────────┐
 │ Page web│──▶│ API │──▶│ pretraitement ─▶ MS1 ─▶ ocr ─▶ MS2 ─▶ extraction │──▶│ MS3 ─▶ PostgreSQL │
 └─────────┘   └─────┘   └───────────────────────────────────────────┘   └─────────────┘
```

1. **API** (`api.py`) : reçoit le fichier, le range dans `storage/`, crée une
   ligne en base et dépose un message dans la file `pretraitement`.
2. **MS1** (`ms1_pretraitement.py`) : PDF ou image → images en niveaux de gris,
   agrandies et redressées.
3. **MS2** (`ms2_ocr.py`) : lit le texte avec Tesseract (français).
4. **MS3** (`ms3_extraction.py`, sur Fedora) : trouve l'enseigne (modèle
   entraîné), la date et le total (règles), puis écrit le résultat en base.

Chaque service lit sa file RabbitMQ, travaille, puis dépose le résultat dans
la file suivante. En cas d'erreur, la cause part dans la file `erreurs` et
MS3 passe le document en `FAILED`. Le code commun tient dans `commun.py`.

| Fichier | Rôle | Lignes |
|---|---|---:|
| `commun.py` | Files RabbitMQ, boucle de lecture des messages | ~100 |
| `api.py` | Dépôt et consultation (FastAPI) | ~120 |
| `ms1_pretraitement.py` | MS1 | ~90 |
| `ms2_ocr.py` | MS2 | ~35 |
| `ms3_extraction.py` | MS3 : règles, modèle, base | ~170 |
| `entrainement.py` | Entraîne le modèle d'enseigne et l'évalue | ~100 |
| `mesures.py` | Mesures de temps | ~60 |
| `index.html` | Page web : glisser-déposer + tableau | ~85 |
| `schema.sql` | La table `documents` (une seule table) | ~20 |
| `docker-compose.yml`, `Dockerfile` | Côté Mac | |
| `fedora/` | Installation de PostgreSQL et MS3 sur la VM | |

### Statuts d'un document

`PENDING` (ligne créée) → `PROCESSING` (parti dans la chaîne) → `COMPLETED`
(résultat en base) ou `FAILED` (avec la cause dans la colonne `erreur`).

### Ce qui est appris, ce qui ne l'est pas

| Champ | Méthode |
|---|---|
| Enseigne | **Modèle entraîné** : TF-IDF sur des morceaux de 2 à 4 lettres + régression logistique |
| Date | Règle : première date valide du ticket |
| Total | Règle : montant de la ligne « TOTAL A PAYER », « A PAYER », « MONTANT DU »… |

Le modèle sert surtout pour Intermarché, dont le logo n'est pas lisible par
l'OCR : les règles ne trouvent alors pas le mot « INTERMARCHE ». Résultat sur
28 tickets de test jamais vus pendant l'entraînement
([reports/evaluation.md](reports/evaluation.md)) :

| | Enseigne (règles) | Enseigne (modèle) | Date | Total |
|---|---:|---:|---:|---:|
| Tous (28) | 89 % | **100 %** | 100 % | 100 % |
| dont Intermarché (3) | 0 % | **100 %** | 100 % | 100 % |

Avec 28 tickets de test, dont 3 Intermarché, ces chiffres montrent une
tendance et ne garantissent pas une performance.

### Fiabilité

- Les files et les messages sont **persistants** : si MS2 s'arrête, les
  tickets attendent dans la file `ocr` et repartent dès qu'il redémarre.
- Un message n'est retiré de la file qu'**après** son traitement.
- MS3 fait un `UPDATE` sur l'identifiant du document : recevoir deux fois le
  même message **ne crée pas de doublon**.
- Si RabbitMQ disparaît, un service s'arrête puis est relancé
  automatiquement, par Docker sur le Mac et par systemd sur Fedora.

---

## Installation (une seule fois)

Prérequis : Docker Desktop sur le Mac, et la VM `docflow-vm` installée selon
[docs/installation_vm_fedora.md](docs/installation_vm_fedora.md).

**1. Mots de passe** : copier le modèle, puis changer les deux mots de passe dans `.env`.

```bash
cp .env.example .env
```

**2. Démarrer la VM** (VirtualBox → `docflow-vm` → Démarrer), puis vérifier le réseau :

```bash
./verifier_reseau.sh
```

**3. Construire et lancer la partie Mac :**

```bash
docker compose up -d --build
```

**4. Entraîner le modèle d'enseigne** (≈ 20 s, tickets dans `data/raw/`) :

```bash
docker compose run --rm outils python entrainement.py
```

**5. Copier la partie Fedora dans la VM :**

```bash
ssh dfadmin@192.168.56.10 mkdir -p docflow
```

```bash
scp -r .env commun.py ms3_extraction.py schema.sql requirements-ms3.txt fedora models dfadmin@192.168.56.10:docflow/
```

**6. Installer PostgreSQL et MS3 dans la VM** (le mot de passe `sudo` est demandé) :

```bash
ssh -t dfadmin@192.168.56.10 sudo bash docflow/fedora/installer.sh
```

La dernière ligne doit afficher `active`. Refaire les étapes 5 et 6 après
chaque modification de `ms3_extraction.py` ou du modèle.

---

## Utilisation (à chaque session)

**1.** Démarrer la VM. PostgreSQL et MS3 démarrent avec elle.

**2.** Démarrer Docker Desktop, puis :

```bash
docker compose up -d
```

Lancer la VM **avant** cette commande : RabbitMQ s'ouvre sur l'adresse
`192.168.56.1`, qui n'existe que lorsque la VM tourne.

**3.** Ouvrir **<http://localhost:8000>** et glisser des tickets dans le rectangle.

En ligne de commande :

```bash
curl -F "fichier=@data/raw/lidl/<fichier>.png" http://localhost:8000/documents
```

```bash
curl http://localhost:8000/documents/DOC-XXXXXXXX
```

```bash
curl http://localhost:8000/health
```

Documentation interactive de l'API : <http://localhost:8000/docs>.

---

## Démonstration

| Montrer | Commande |
|---|---|
| Les files RabbitMQ | <http://localhost:15672> (utilisateur `docflow`, mot de passe de `.env`) |
| MS1 et MS2 qui travaillent (Mac) | `docker compose logs -f ms1 ms2` |
| MS3 qui travaille (Fedora) | `ssh -t dfadmin@192.168.56.10 sudo journalctl -u docflow-ms3 -f` |
| Le contenu de la base | voir ci-dessous |
| Panne de MS2 | `docker compose stop ms2`, déposer un ticket (il reste `PROCESSING`), puis `docker compose start ms2` |
| Plus de lecteurs OCR | `docker compose up -d --scale ms2=3` |
| Mesures de temps | `docker compose run --rm outils python mesures.py 30` → `reports/mesures.md` |

Contenu de la base, depuis le Mac :

```bash
ssh -t dfadmin@192.168.56.10 "sudo -u postgres psql docflow -c 'SELECT document_id, status, entity, date, total_amount FROM documents ORDER BY created_at DESC LIMIT 10'"
```

---

## Arrêter

```bash
docker compose down
```

Puis éteindre la VM depuis VirtualBox.

## Dépannage

| Problème | Solution |
|---|---|
| `bind: can't assign requested address 192.168.56.1` | La VM n'est pas démarrée : la lancer, puis `docker compose up -d` |
| `/health` indique `"base": "injoignable"` | VM éteinte, ou PostgreSQL arrêté : `ssh -t dfadmin@192.168.56.10 systemctl status postgresql` |
| Tickets bloqués en `PROCESSING` | Regarder le journal de MS3 (commande ci-dessus) |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | Voir la section Dépannage de [docs/installation_vm_fedora.md](docs/installation_vm_fedora.md) |

## Confidentialité

Les tickets (`data/`), les fichiers déposés (`storage/`), le modèle
(`models/`) et `.env` ne sont jamais envoyés sur Git (voir `.gitignore`). Les
fichiers déposés sont renommés `DOC-…` : leur nom d'origine n'est conservé nulle part.
