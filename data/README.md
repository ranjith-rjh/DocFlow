# Données privées — tickets de caisse

> ⚠️ Le contenu de ce dossier est **ignoré par Git** (voir `.gitignore`).
> Seuls ce README et les fichiers `.gitkeep` sont versionnés.

## Organisation

| Dossier | Contenu |
|---|---|
| `raw/carrefour/` | Tickets Carrefour |
| `raw/lidl/` | Tickets Lidl |
| `raw/intermarche/` | Tickets Intermarché |
| `raw/a_trier/` | Tickets dont l'enseigne est douteuse ou illisible |
| `annotations/` | Fiches de vérité de référence (générées à partir des noms de fichiers) |

## Convention de nommage

```
<entite>_<AAAA>-<JJ>-<MM>_<montant_total>.<extension>
```

Exemple : `carrefour_2025-17-04_12.34.pdf` → Carrefour, **17 avril 2025**, total 12,34 €.

- `entite` : `carrefour`, `lidl` ou `intermarche` (minuscules, sans accent).
- Date dans l'ordre **année – jour – mois**.
- Montant avec un point décimal et deux décimales.

**Le nom du fichier est la vérité de référence** saisie à la main. Il sert à
générer les annotations, mais **ne doit jamais être lu par la pipeline** : à
l'upload, le fichier est renommé avec son `document_id`, sinon l'extraction
« tricherait ».

Si plusieurs fichiers représentent **le même ticket physique**, ajouter un
suffixe après le montant (`..._19.41_b.pdf`) pour qu'ils restent dans le même
groupe d'entraînement ou de test (cahier des charges §8.3).

## Inventaire au 16/11/2026

| Enseigne | Tickets | Format | Période |
|---|---:|---|---|
| Carrefour | 81 | PDF avec couche texte (64 × 1 page, 17 × 2 pages) | 2025 – 2026 |
| Lidl | 40 | PNG, largeur 412 px (captures d'application) | 2023 – 2026 |
| Intermarché | 16 | PDF image, sans couche texte | 2025 – 2026 |
| **Total** | **137** | | |

Tous les noms respectent la convention et toutes les dates sont valides.
