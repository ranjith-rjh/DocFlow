# Corpus et découpage

> Chiffres agrégés uniquement : les tickets et leurs annotations restent dans
> `data/` (ignoré par Git).

## Origine

Tickets personnels, annotés par leur nom de fichier (décision D-04) :
`<entite>_<AAAA>-<JJ>-<MM>_<montant>.<ext>`. Générés par
`python -m training.corpus`.

| Enseigne | Fichiers | Format | Remarque |
|---|---:|---|---|
| Carrefour | 81 | PDF A4 (e-ticket), couche texte | 17 tickets sur 2 pages |
| Lidl | 40 | PNG 412 px de large (captures d'application) | police de ~10 px ; certains contiennent une section « Retour » |
| Intermarché | 16 | PDF long (ticket scanné/numérique), couche texte | logo stylisé, illisible par l'OCR |
| **Total** | **137** | | **136 tickets distincts** |

Regroupement prudent : deux fichiers de la même enseigne, même montant, à
≤ 3 jours d'écart sont placés dans le même groupe (1 cas Carrefour, Q-04).

## Découpage figé (graine 42)

Stratifié par enseigne, groupé par ticket, `ceil(15 %)` en validation et en
test. Créé **avant** toute expérience, jamais régénéré
(`data/annotations/split.csv`).

| Enseigne | Entraînement | Validation | Test |
|---|---:|---:|---:|
| Carrefour | 57 | 12 | 12 |
| Lidl | 28 | 6 | 6 |
| Intermarché | 10 | 3 | 3 |
| **Total** | **95** | **21** | **21** |

## Limites connues

- **Aucune photo de ticket papier** : pas d'inclinaison, de froissure ni de
  mauvais éclairage réels (décision D-03 : inclinaisons simulées pour T-02).
- **Format corrélé à l'enseigne** (Lidl = PNG, autres = PDF). MS1 ramène tout
  au même format (D-02), mais la qualité de source reste propre à chaque
  enseigne : les résultats par enseigne reflètent aussi cette qualité.
- **Intermarché : 3 tickets de test seulement.** Les taux par enseigne sur le
  test ont une très forte incertitude (1 erreur = 33 points).
