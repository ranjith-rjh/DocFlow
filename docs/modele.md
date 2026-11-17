# Fiche du modèle `docflow-extraction-1.0.0`

> Générée par `python -m training.entrainement` le 2026-11-16T20:48:04+00:00.
> L'artefact (`models/docflow-extraction.joblib`) n'est pas versionné dans Git :
> il est construit à partir des tickets privés.

## Ce qui est appris (§8.4)

| Champ | Candidats | Choix | Statut |
|---|---|---|---|
| Enseigne | texte OCR complet, chiffres masqués | TF-IDF n-grammes de caractères (2–4) + régression logistique ; `UNKNOWN` si probabilité < 0,55 | **appris** |
| Total | règles : tous les montants à 2 décimales | régression logistique sur le contexte de chaque montant (mots de la ligne et des voisines, position, rang, fréquence) | **hybride** (candidats par règles, choix appris) |
| Date | règles : toutes les dates plausibles | régression logistique sur le contexte (heure sur la ligne, fréquence, position, mots-clés) | **hybride** (candidats par règles, choix appris) |

Si un champ n'a aucun candidat, ou si le modèle d'enseigne est incertain
(mise en page jamais vue), l'extracteur retombe sur la baseline et le signale
(`methode = regles` ou `aucun`) ; aucune valeur n'est inventée.

## Données

116 documents (partitions *train* + *validation*) :
CARREFOUR 69, INTERMARCHE 13, LIDL 34.
Le jeu de test (21 fichiers) n'a jamais été utilisé pour l'entraînement ni pour
le choix des hyperparamètres.

## Validation croisée groupée (5 plis, train + validation)

| C | Enseigne | Date | Total |
|---|---:|---:|---:|
| 0.1 | 10.3% | 99.1% | 99.1% |
| 0.3 | 100.0% | 99.1% | 99.1% |
| 1.0 | 100.0% | 99.1% | 99.1% |
| 3.0 | 100.0% | 99.1% | 99.1% |
| 10.0 | 100.0% | 99.1% | 99.1% |

**Retenu par champ** : {'entity': 0.3, 'total_amount': 0.1, 'date': 0.1}

| Méthode | Enseigne | Date | Total |
|---|---:|---:|---:|
| Baseline règles (sans apprentissage) | 93.1% | 99.1% | 99.1% |
| Modèle (validation croisée) | 100.0% | 99.1% | 99.1% |

La baseline n'apprend rien : son score sur train + validation est directement
comparable. Le résultat final, sur le test indépendant, est dans
`reports/evaluation_finale.md`.

## Environnement

Python 3.12.8, scikit-learn 1.9.1
(version figée dans `pyproject.toml` pour charger l'artefact à l'identique sur Fedora).
