# Évaluation

## Baseline par règles — partitions ['train', 'validation']

### Exactitude

| Enseigne | n | Entité | Date | Total | Document entièrement correct |
|---|---:|---:|---:|---:|---:|
| CARREFOUR | 69 | 100.0% | 98.6% | 100.0% | 98.6% |
| INTERMARCHE | 13 | 38.5% | 100.0% | 100.0% | 38.5% |
| LIDL | 34 | 100.0% | 100.0% | 97.1% | 97.1% |
| **GLOBAL** | 116 | 93.1% | 99.1% | 99.1% | 91.4% |

### Enseigne : précision, rappel, F1

| Enseigne | Précision | Rappel | F1 |
|---|---:|---:|---:|
| CARREFOUR | 100.0% | 100.0% | 100.0% |
| INTERMARCHE | 100.0% | 38.5% | 55.6% |
| LIDL | 100.0% | 100.0% | 100.0% |

### Types d'erreurs

| Enseigne | Champ | Type d'erreur | Nombre |
|---|---|---|---:|
| CARREFOUR | date | autre date du ticket | 1 |
| INTERMARCHE | entity | valeur absente | 8 |
| LIDL | total_amount | montant trop élevé | 1 |

### Qualité OCR (PDF, couche texte comme référence)

Approximation : l'ordre de lecture de la couche texte peut différer de celui de l'OCR, ce qui augmente artificiellement le CER.

| Enseigne | n | CER moyen | WER moyen |
|---|---:|---:|---:|
| CARREFOUR | 69 | 6.5% | 8.1% |
| INTERMARCHE | 13 | 10.4% | 9.8% |
