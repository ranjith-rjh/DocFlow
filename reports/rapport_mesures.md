# Rapport de mesures — DocFlow AI

> Ticket DF-29. Seuls des résultats **réellement exécutés** figurent ici ; ce
> qui reste à mesurer est signalé comme tel. Détails bruts : `reports/mesures/`
> (agrégats versionnés) et `reports/raw/` (privé, ignoré par Git).

## 1. Environnement de mesure

| Élément | Valeur |
|---|---|
| Machine | MacBook Pro M4 Pro, 12 cœurs, 24 Go, macOS 27.2.1 |
| Conteneurs | Docker Desktop 29.9.2 (VM Docker : 12 CPU, 7,7 Go) |
| VM | VirtualBox 7.2.22, Fedora 45 aarch64, 4 vCPU, 8 Go |
| OCR | Tesseract 5 (`fra`, `--oem 1 --psm 4`), un thread par worker |
| Modèle | `docflow-extraction-1.0.0`, scikit-learn 1.9.1 |
| Date | 2026-11-16 |

## 2. Qualité d'extraction (§11.1, T-11)

Jeu de test indépendant : 21 fichiers (12 Carrefour, 6 Lidl, 3 Intermarché),
jamais utilisés pour l'entraînement ni les réglages. Rapports :
`evaluation_finale.md` (+ erratum) et `evaluation_finale_corrigee.md`.

| Méthode | Entité | Date | Total | Document entièrement correct |
|---|---:|---:|---:|---:|
| Baseline par règles | 95,2 % | 100 % | 100 % | 95,2 % |
| **Modèle hybride entraîné** | **100 %** | **100 %** | **100 %** | **100 %** |

Validation croisée groupée (5 plis, 116 fichiers train + validation) :
enseigne 100 % (règles 93,1 %), date 99,1 %, total 99,1 % (égaux aux règles).

**Ce que l'apprentissage apporte réellement :** la reconnaissance de
l'enseigne quand son nom n'est pas lisible (logo Intermarché stylisé, ignoré
par l'OCR). Pour la date et le total, le choix appris égale les règles : les
erreurs restantes en validation croisée viennent de **l'OCR** (dans 3 cas
sur 4, la bonne valeur n'a pas été lue), pas de la sélection.

**Qualité OCR** (couche texte des PDF comme référence, approximation) :
Carrefour CER 5,2 % / WER 7,8 % ; Intermarché CER 10,2 % / WER 12,7 % (test).
Passer le rendu PDF de 200 à 300 DPI a fait baisser le CER Carrefour de
11,4 % à 6,5 % (mesuré sur train + validation).

**Prudence :** 21 documents de test, dont 3 Intermarché ; une erreur vaut
4,8 points au global et 33 points pour Intermarché. Pas de photo de ticket
papier dans le corpus (D-03) : la robustesse aux photos réelles n'est pas
démontrée, seulement des inclinaisons simulées (T-02 réussi à 6° et 7°).

## 3. Performance (§11.2)

**Mode mesuré : nœud B local** (MS3 + PostgreSQL en conteneurs sur le Mac).
Les mesures en **mode distribué** (MS3 sur Fedora) restent à faire avec la
VM : `./scripts/benchmark.py` (même protocole).

Protocole : 3 documents d'échauffement non comptés, sélection déterministe
alternant les enseignes (`benchmark.choisir_fichiers`), 1 répétition.

### 3.1 Latence à vide (un document à la fois, 20 documents)

| Étape | Moyenne | Médiane | p95 |
|---|---:|---:|---:|
| MS1 prétraitement | 141 ms | — | — |
| MS2 OCR | 1 072 ms | — | — |
| MS3 extraction + écriture | 3 ms | — | — |
| Attente dans les files (total) | ≈ 13 ms | — | — |
| **Bout en bout (dépôt → résultat)** | **1 236 ms** | 1 341 ms | 2 248 ms |

### 3.2 Monolithe contre distribué (mêmes 20 fichiers, un à la fois)

| Version | Latence moyenne | Médiane |
|---|---:|---:|
| Monolithe (`pipeline_locale.py`, un seul processus) | 1 182 ms | 1 307 ms |
| Distribué, mode nœud B local | 1 236 ms | 1 341 ms |
| **Surcoût messagerie + base** | **+54 ms (+4,6 %)** | |

La distribution ne rend pas un document plus rapide : elle coûte ~50 ms de
communication. Son intérêt est ailleurs (ci-dessous).

### 3.3 Charge (60 documents déposés d'un coup)

| Configuration | Débit | Bout en bout moyen | p95 | Attente moyenne file OCR |
|---|---:|---:|---:|---:|
| 1 × MS2 | 54,8 docs/min | 34,9 s | 62,8 s | 29,3 s |
| **3 × MS2** (`--scale ms2=3`) | **157,6 docs/min** | 12,1 s | 21,7 s | 6,6 s |

Le goulot est l'OCR (≈ 90 % du temps de traitement). Ajouter deux workers
MS2, **sans modifier une ligne de code**, multiplie le débit par 2,9 : c'est
le bénéfice concret du découpage en microservices et de la file RabbitMQ
(l'« atelier » du §4.1 qui ajoute un second lecteur).

### 3.4 Panne et reprise (T-07)

MS2 arrêté pendant un dépôt : la tâche reste dans `docflow.ms2.ocr`, le
document reste `PENDING`/`PROCESSING`, puis passe `COMPLETED` au redémarrage
de MS2, sans perte (test automatisé, voir `docs/journal_tests.md`).

## 4. Coût environnemental estimé (§11.3, T-12)

**Pas encore mesuré.** `powermetrics` (seul moyen de mesurer la puissance de
la puce sur Apple Silicon) demande les droits administrateur ; la mesure doit
être lancée par l'utilisateur :

```bash
./scripts/mesurer_energie.sh
```

Méthode : puissance moyenne du SoC (CPU + GPU + ANE) au repos pendant 30 s,
puis pendant le traitement de 60 documents ; énergie nette = (charge − repos)
× durée ; Wh/document ; gCO₂e/document avec un facteur d'intensité carbone
paramétrable (`FACTEUR_CO2_G_KWH`, 52 g/kWh par défaut : valeur indicative du
mix électrique français, **à vérifier et citer** depuis la Base Empreinte ADEME).

Limites : périmètre limité à la puce (ni écran, ni RAM, ni alimentation) ;
la consommation propre de Docker Desktop et de VirtualBox est incluse sans
pouvoir être isolée ; autres applications à fermer pendant la mesure.

## 5. Reste à faire

| Mesure | Bloquant | Commande |
|---|---|---|
| Performance en mode distribué (Mac ↔ Fedora) | VM démarrée + `deployer_noeud_b.sh` | `scripts/benchmark.py` |
| Énergie | droits sudo | `scripts/mesurer_energie.sh` |
| Tests d'acceptation en mode distribué | idem | `pytest -m integration` |
