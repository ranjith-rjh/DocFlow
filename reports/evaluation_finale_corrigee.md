# Évaluation finale corrigée — jeu de test indépendant

> **Réévaluation corrective.** Raison : un fichier Intermarché du test avait été évalué avec un OCR en cache périmé (rendu 200 DPI), car son prétraitement à 300 DPI échouait (page > 60 Mpx). Bug corrigé (résolution réduite pour les pages très longues uniquement), cache entièrement régénéré sans échec ; modèle inchangé.

> Exécutée une seule fois, le 2026-11-16, avec le modèle
> `docflow-extraction-1.0.0` et la baseline figés. 21 fichiers jamais vus
> pendant l'entraînement ni la mise au point (12 Carrefour, 6 Lidl, 3 Intermarché).

## Synthèse : baseline contre modèle, même jeu de test

| Méthode | Entité | Date | Total | Document entièrement correct |
|---|---:|---:|---:|---:|
| Baseline par règles | 95.2% | 100.0% | 100.0% | 95.2% |
| Modèle hybride entraîné | 100.0% | 100.0% | 100.0% | 100.0% |

**Lecture prudente :** avec 21 documents, une erreur vaut 4,8 points au global
et 33 points pour Intermarché (3 documents). Ces chiffres montrent une
tendance, pas une performance garantie.

## Méthode réellement utilisée par champ (modèle hybride)

| Champ | Nombre de documents |
|---|---|
| date | modele : 21 |
| entity | modele : 21 |
| total_amount | modele : 21 |

## Détail — baseline par règles

### Exactitude

| Enseigne | n | Entité | Date | Total | Document entièrement correct |
|---|---:|---:|---:|---:|---:|
| CARREFOUR | 12 | 100.0% | 100.0% | 100.0% | 100.0% |
| INTERMARCHE | 3 | 66.7% | 100.0% | 100.0% | 66.7% |
| LIDL | 6 | 100.0% | 100.0% | 100.0% | 100.0% |
| **GLOBAL** | 21 | 95.2% | 100.0% | 100.0% | 95.2% |

### Enseigne : précision, rappel, F1

| Enseigne | Précision | Rappel | F1 |
|---|---:|---:|---:|
| CARREFOUR | 100.0% | 100.0% | 100.0% |
| INTERMARCHE | 100.0% | 66.7% | 80.0% |
| LIDL | 100.0% | 100.0% | 100.0% |

### Types d'erreurs

| Enseigne | Champ | Type d'erreur | Nombre |
|---|---|---|---:|
| INTERMARCHE | entity | valeur absente | 1 |

## Détail — modèle hybride entraîné

### Exactitude

| Enseigne | n | Entité | Date | Total | Document entièrement correct |
|---|---:|---:|---:|---:|---:|
| CARREFOUR | 12 | 100.0% | 100.0% | 100.0% | 100.0% |
| INTERMARCHE | 3 | 100.0% | 100.0% | 100.0% | 100.0% |
| LIDL | 6 | 100.0% | 100.0% | 100.0% | 100.0% |
| **GLOBAL** | 21 | 100.0% | 100.0% | 100.0% | 100.0% |

### Enseigne : précision, rappel, F1

| Enseigne | Précision | Rappel | F1 |
|---|---:|---:|---:|
| CARREFOUR | 100.0% | 100.0% | 100.0% |
| INTERMARCHE | 100.0% | 100.0% | 100.0% |
| LIDL | 100.0% | 100.0% | 100.0% |

### Types d'erreurs

_Aucune erreur._

### Qualité OCR (PDF, couche texte comme référence)

Approximation : l'ordre de lecture de la couche texte peut différer de celui de l'OCR, ce qui augmente artificiellement le CER.

| Enseigne | n | CER moyen | WER moyen |
|---|---:|---:|---:|
| CARREFOUR | 12 | 5.2% | 7.8% |
| INTERMARCHE | 3 | 10.2% | 12.7% |
