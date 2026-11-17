# Backlog DocFlow AI

> Découpage du cahier des charges en tickets de travail, phases P2 à P7 (§13).
> Un ticket = un objectif vérifiable = au moins un commit `DF-xx : …`.
>
> **Statuts :** ⬜ à faire · 🔄 en cours · ✅ terminé · ⏸️ bloqué
> **Réf. CDC** = section ou exigence du cahier des charges couverte.

## Vue d'ensemble

| Phase | Tickets | But |
|---|---|---|
| P1 — Préparation | DF-00 ✅ | Corpus inventorié, VM et réseau validés |
| P2 — Prototype local | DF-01 → DF-07 | Un ticket va de l'image au JSON, sans réseau |
| P3 — Microservices | DF-08 → DF-13 | API, MS1, MS2, MS3 isolés, contrats figés |
| P4 — Distribution | DF-14 → DF-16 | Docker Mac ↔ RabbitMQ ↔ MS3 Fedora |
| P5 — Stockage et supervision | DF-17 → DF-19 | PostgreSQL, statuts, journaux, idempotence |
| P6 — Entraînement | DF-20 → DF-24 | Modèle entraîné comparé à la baseline |
| P7 — Validation finale | DF-25 → DF-30 | Test final, pannes, mesures, rapport, démo |

## Décisions à trancher (bloquent certains tickets)

| ID | Question | Recommandation | Bloque | Qui |
|---|---|---|---|---|
| Q-01 | RabbitMQ confirmé comme messagerie ? (§14) | Oui | DF-08 | Encadrant |
| Q-02 | Faut-il distribuer la base elle-même (réplication / partitionnement) ? (§7.3) | Non en V1 ; extension si exigée | DF-18 | Encadrant |
| Q-03 | Qui écrit les statuts en base ? (§6.2) | L'API crée la ligne `PENDING` et lit les résultats ; MS1/MS2/MS3 écrivent leur étape dans un journal via un compte restreint ; MS3 écrit le résultat | DF-09, DF-18 | Nous |
| Q-04 | Deux tickets Carrefour de même montant, à un jour d'écart : même ticket ? | **Tranché** : regroupés par prudence dans le même groupe (voir `docs/corpus.md`) | DF-02 | Nous |
| Q-05 | Comment MS3 lance-t-il sur Fedora ? | Environnement virtuel Python + service `systemd` (pas de Docker dans la VM, pour garder la distinction conteneur / VM) | DF-15 | Nous |

---

## P1 — Préparation

### DF-00 ✅ Corpus, VM et réseau
- Inventaire : 137 tickets (Carrefour 81, Lidl 40, Intermarché 16), noms validés.
- VM `docflow-vm` Fedora 45, `docflow-net` en `192.168.56.10`, test T-10 réussi.
- Reste : instantané VirtualBox `base-reseau-ok`.

> **État au 2026-11-16** : tout est implémenté et testé en mode « nœud B local ». À exécuter avec la VM : DF-15/16 (déploiement réel de MS3 sur Fedora), DF-28 (énergie, sudo).

---

## P2 — Prototype local

### DF-01 ✅ Squelette du dépôt et outillage
- **Objectif :** une structure claire, avant le premier module.
- **Livrables :** `pyproject.toml`, `ruff`, `pytest`, `README.md` (rôle de chaque dossier), `.env.example`.
  Arborescence réalisée : un paquet `src/docflow/` avec un sous-paquet par composant (`api`, `pretraitement` = MS1, `ocr` = MS2, `extraction` = MS3, `commun`) et des dépendances optionnelles par microservice ; `training/`, `scripts/`, `tests/`.
- **Fini quand :** `pytest` et `ruff check` passent sur le dépôt vide.
- **Réf. CDC :** §9.3, NF-04, NF-09.

### DF-02 ✅ Vérité de référence à partir des noms de fichiers
- **Objectif :** produire les annotations sans ressaisie (D-04).
- **Livrables :** `scripts/generer_annotations.py` → `data/annotations/annotations.csv` (fichier, entité, date ISO, montant en texte, devise, identifiant de groupe) ; tests du parseur (date `AAAA-JJ-MM`, montant, suffixe `_b`).
- **Fini quand :** 137 lignes, aucune erreur, effectifs par enseigne affichés. Q-04 tranchée.
- **Réf. CDC :** §8.2.

### DF-03 ✅ Découpage entraînement / validation / test figé
- **Objectif :** séparer les données **avant** toute expérience.
- **Livrables :** `scripts/decouper_corpus.py` (stratifié par enseigne, groupé par ticket, graine fixe) → `data/annotations/split.csv` ; effectifs réels publiés dans `docs/corpus.md` (chiffres agrégés uniquement).
- **Fini quand :** chaque enseigne est présente dans chaque groupe ; le test n'est plus jamais modifié. Vu la taille d'Intermarché (16), validation croisée groupée sur entraînement + validation.
- **Réf. CDC :** §8.3.

### DF-04 ✅ Module de prétraitement (futur cœur de MS1)
- **Objectif :** tout document → image(s) dans **un format unique** (D-02).
- **Livrables :** PDF → une image par page (PyMuPDF, résolution fixe), PNG/JPG chargés, niveaux de gris, redressement / rotation, débruitage léger, redimensionnement ; contrôle du type réel du fichier ; tests sur fichiers synthétiques (aucun ticket réel dans les tests versionnés).
- **Fini quand :** les 137 tickets passent sans erreur ; sorties visuellement contrôlées sur un échantillon de chaque enseigne.
- **Réf. CDC :** §4.2, T-02, T-03, T-04.

### DF-05 ✅ Module OCR (futur cœur de MS2)
- **Objectif :** lire le texte des images préparées.
- **Livrables :** Tesseract `fra` via `pytesseract`, texte par page dans l'ordre, mots avec position et confiance, pages vides signalées, durée mesurée.
- **Fini quand :** OCR exécuté sur tout le corpus ; **CER/WER** calculés sur les Carrefour avec leur couche texte PDF comme référence.
- **Réf. CDC :** §4.3, §11.1.

### DF-06 ✅ Baseline d'extraction par règles (futur MS3)
- **Objectif :** point de comparaison simple et honnête.
- **Livrables :** entité par mots-clés (`UNKNOWN` sinon), date du ticket, total TTC par mots-clés (`TOTAL`, `À PAYER`…), normalisation (`Decimal`, ISO, EUR), `null` si absent ; tests unitaires des normalisations (€, espaces insécables, virgules).
- **Fini quand :** les fonctions sont testées et ne devinent jamais une valeur absente.
- **Réf. CDC :** §4.4, §6.3.

### DF-07 ✅ Pipeline locale monolithique et premier benchmark
- **Objectif :** enchaîner DF-04 → DF-05 → DF-06 en un seul programme.
- **Livrables :** `scripts/pipeline_locale.py fichier → JSON` ; rapport de la baseline **sur entraînement + validation uniquement** (exactitude par champ et par enseigne, durée par étape).
- **Fini quand :** un ticket de chaque enseigne produit le JSON attendu ; ce monolithe sert de référence pour la comparaison du §11.2.
- **Réf. CDC :** P2, §11.2.

---

## P3 — Microservices

### DF-08 ✅ Contrats de messages et conventions RabbitMQ
- **Livrables :** modèles Pydantic des 5 événements (§6.1), version de contrat `v1`, noms d'exchange et de files, `correlation_id`. Choix : le texte OCR voyage **dans** `ocr.completed` (MS3 n'a pas accès au stockage du Mac) ; les images ne voyagent jamais. Documentation dans `docs/contrats.md`.
- **Fini quand :** contrats testés (sérialisation aller-retour, rejet des messages invalides).
- **Réf. CDC :** §6.1, §9.2, NF-10.

### DF-09 ✅ API FastAPI
- **Livrables :** `POST /documents` (contrôle du contenu réel, limites de taille et de pages, renommage en `document_id`, `202`), `GET /documents/{id}`, `GET /health` ; codes HTTP justes (415, 413, 404, 503) ; messages d'erreur sans données sensibles.
- **Fini quand :** tests de l'API avec messagerie et base simulées ; T-05 couvert.
- **Réf. CDC :** §9.1, F-01 à F-05.

### DF-10 ✅ Socle commun des workers
- **Livrables :** connexion RabbitMQ résiliente, acquittement **après** succès, files et messages persistants, tentatives limitées puis file d'erreur, journaux contextualisés par `document_id`, configuration par variables d'environnement.
- **Fini quand :** testé sur un RabbitMQ local (redémarrage du broker, message invalide → file d'erreur).
- **Réf. CDC :** §6.3, NF-05.

### DF-11 ✅ MS1 — service de prétraitement
- DF-04 branché sur DF-10 : consomme `document.received`, publie `preprocessing.completed`.
- **Fini quand :** lancé et testé seul (NF-01).

### DF-12 ✅ MS2 — service OCR
- DF-05 branché sur DF-10 : consomme `preprocessing.completed`, publie `ocr.completed`.
- **Fini quand :** lancé et testé seul.

### DF-13 ✅ MS3 — service d'extraction et d'insertion
- DF-06 (puis le modèle de P6) branché sur DF-10 : consomme `ocr.completed`, écrit en base, publie `extraction.completed`.
- **Fini quand :** lancé et testé seul, base de test locale.

---

## P4 — Distribution

### DF-14 ✅ Docker Compose côté Mac
- **Livrables :** `docker-compose.yml` (API, MS1, MS2, RabbitMQ avec console d'administration, volume de stockage) ; RabbitMQ exposé sur `192.168.56.1` uniquement ; images figées par version.
- **Fini quand :** `docker compose up` démarre tout ; T-01 réussi jusqu'à `ocr.completed`.
- **Réf. CDC :** §5, NF-02.

### DF-15 🔄 Déploiement de MS3 sur Fedora
- **Livrables :** script d'installation (environnement virtuel, dépendances figées), service `systemd` `docflow-ms3`, variables d'environnement, guide pas à pas (Q-05).
- **Fini quand :** MS3 consomme depuis RabbitMQ sur le Mac ; flux visibles sur le réseau (NF-02).

### DF-16 🔄 Bout en bout distribué
- **Fini quand :** T-01, T-03, T-09 réussis à travers les deux nœuds, avec et sans Wi-Fi ; `scripts/verifier_reseau.sh` étendu au port RabbitMQ.

---

## P5 — Stockage et supervision

### DF-17 ✅ PostgreSQL sur Fedora
- **Livrables :** installation, base `docflow`, comptes séparés (MS3 en écriture, API en lecture + création `PENDING`, workers en journal seulement — Q-03), accès limité à `192.168.56.0/24`, guide.
- **Fini quand :** connexions testées depuis le Mac et depuis un conteneur.

### DF-18 ✅ Schéma, migrations et idempotence
- **Livrables :** tables `documents`, `resultats`, `journal_etapes` ; montant en `NUMERIC(10,2)` ; insertion idempotente sur `document_id` ; scripts de création / migration versionnés.
- **Fini quand :** T-08 (événement republié → pas de doublon) automatisé.
- **Réf. CDC :** §7.2, NF-07.

### DF-19 ✅ Traçabilité
- **Livrables :** statut et durée de chaque étape visibles via `GET /documents/{id}` ; journaux structurés sans contenu de ticket.
- **Fini quand :** pour un document, on retrouve étapes, durées et erreurs (NF-06).

---

## P6 — Entraînement

### DF-20 ✅ Jeu de données d'entraînement
- **Livrables :** textes OCR du corpus via la pipeline, génération des **candidats** (montants, dates) avec leurs caractéristiques (mots voisins, position verticale, ligne, format) et l'étiquette « bon / mauvais » issue des annotations.
- **Fini quand :** jeu construit à partir de l'entraînement et de la validation uniquement.

### DF-21 ✅ Classifieur d'enseigne
- TF-IDF (caractères) + régression logistique, validation croisée groupée, comparé aux mots-clés.

### DF-22 ✅ Sélection apprise de la date et du total
- Classifieur de candidats (régression logistique ou forêt aléatoire, selon la validation) ; repli sur les règles si aucun candidat n'est sûr → système **hybride documenté**.

### DF-23 ✅ Artefact versionné et intégration dans MS3
- **Livrables :** modèle sauvegardé avec version, paramètres et métriques de validation (`models/` ignoré par Git ; fiche du modèle versionnée dans `docs/`), chargement par MS3, choix baseline / modèle par configuration.
- **Fini quand :** MS3 sur Fedora utilise l'artefact.

### DF-24 ✅ Fiche « qui fait quoi » par champ
- Tableau honnête : pour l'entité, la date et le montant, ce qui est appris, ce qui est déterministe, ce qui est hybride (§8.4).

---

## P7 — Validation finale

### DF-25 ✅ Évaluation sur le test final (une seule fois)
- Baseline et modèle figés sur **le même** jeu de test : exactitude par champ, document entièrement correct, précision / rappel / F1, global et par enseigne, effectifs publiés, cas d'échec anonymisés. Biais signalé : qualité de source différente selon l'enseigne.
- **Réf. CDC :** §11.1, T-11.

### DF-26 ✅ Tests de panne et de robustesse
- T-07 (arrêt de MS2 pendant un dépôt puis reprise), T-08, message invalide, VM éteinte puis rallumée ; tickets inclinés simulés (D-03) pour T-02 ; total ambigu (T-06).

### DF-27 ✅ Mesures de performance
- Temps de bout en bout et par service, débit, attente dans les files, impact du redémarrage de MS2, **monolithe (DF-07) contre distribué** ; protocole écrit (machine, répétitions, échauffement).
- **Réf. CDC :** §11.2.

### DF-28 🔄 Coût environnemental estimé
- Énergie (Wh, Wh/document) via `powermetrics` sur le Mac, comparaison au repos, gCO₂e/document avec un facteur documenté, limites (Docker et VirtualBox sur Apple Silicon).
- **Réf. CDC :** §11.3, T-12.

### DF-29 ✅ Rapport de mesures
- Synthèse de DF-25 à DF-28, avec méthode et limites.

### DF-30 ✅ Démonstration et documentation finale
- Script de démo en 7 étapes (§12), guide d'installation complet Mac + Fedora, dépannage, mise à jour des schémas d'architecture ; relecture de la checklist du §15.
