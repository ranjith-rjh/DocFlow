# Journal des tests d'acceptation

> Résultats **réellement observés** des tests du §12 du cahier des charges.
> Ne rien inscrire ici qui n'ait pas été exécuté.

| Test | Date | Environnement | Résultat | Preuve |
|---|---|---|---|---|
| T-10 — Réseau privé avec et sans Wi-Fi | 2026-11-16 | Mac M4 Pro (macOS 27.2.1, Docker 29.9.2) ↔ `docflow-vm` Fedora 45 aarch64, VirtualBox 7.2.22, `HostNetwork` | ✅ Réussi | `scripts/verifier_reseau.sh` : 4/4 tests OK avec Wi-Fi puis Wi-Fi coupé (adresse Mac `192.168.56.1`, ping Mac → VM, port SSH 22, ping conteneur Docker → VM). |
| T-01 — JPEG lisible | 2026-11-16 | Mode nœud B local (tout sur le Mac), ticket **synthétique** | ✅ Réussi | `pytest -m integration` : entité, date, total, devise exacts et persistés. |
| T-02 — PNG incliné de 7° | 2026-11-16 | idem | ✅ Réussi | Angle estimé par MS1 à ±1°, total exact. |
| T-03/T-04 — PDF de 2 pages | 2026-11-16 | idem | ✅ Réussi | 2 pages suivies, total en page 2 trouvé. |
| T-05 — Format non supporté / PDF corrompu | 2026-11-16 | idem | ✅ Réussi | HTTP 415 sans plantage ; PDF tronqué → `FAILED` « PDF illisible ou corrompu ». |
| T-06 — Total ambigu | 2026-11-16 | idem | ✅ Réussi | « A payer » choisi face à sous-total, promotion et « TOTAL ELIGIBLE ». Premier essai en police 34 px : « 3,02 » lu « 8,02 » par l'OCR (erreur de lecture, pas de sélection). |
| T-07 — Arrêt de MS2 pendant un dépôt | 2026-11-16 | idem | ✅ Réussi | Message conservé dans `docflow.ms2.ocr`, document `COMPLETED` après redémarrage. |
| T-08 — Événement republié | 2026-11-16 | idem | ✅ Réussi | `ocr.completed` publié deux fois avec le même `event_id` : 1 résultat, 1 ligne de journal. |
| T-09 — Consultation par identifiant | 2026-11-16 | idem | ✅ Réussi | 4 événements métier + 3 `step.started`, durée de bout en bout, 404 si inconnu. |
| T-01 à T-09 avec le modèle actif | 2026-11-16 | Mode nœud B local, modèle `docflow-extraction-1.0.0` | ✅ Réussi (9/9) | Premier essai : T-01 en `UNKNOWN` (modèle incertain sur une mise en page synthétique) → repli sur les règles ajouté, puis 9/9. |
| T-01 à T-04 sur **tickets réels** | 2026-11-16 | Mode nœud B local, partition *validation* | ✅ Réussi (4/4) | `scripts/acceptation_reelle.py` : JPEG Carrefour, PNG Lidl incliné de 6°, PDF Intermarché, PDF Carrefour 2 pages. |
| T-11 — Jeu de test indépendant | 2026-11-16 | 21 fichiers | ✅ Réalisé | Modèle 100 % documents corrects, baseline 95,2 % (`reports/evaluation_finale*.md`, erratum inclus). |
| T-12 — Temps et débit | 2026-11-16 | Mode nœud B local | ✅ Réalisé | `reports/rapport_mesures.md` : 1,24 s à vide, 55 → 158 docs/min avec 3 MS2, surcoût distribué +54 ms. |
| T-12 — Énergie | — | — | ⏳ À exécuter | `scripts/mesurer_energie.sh` (sudo requis). |
| T-01 à T-09 en mode distribué (MS3 sur Fedora) | — | — | ⏳ À exécuter | Après `scripts/deployer_noeud_b.sh`. |
