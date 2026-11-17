# Journal des décisions

> Répond au §14 du cahier des charges (« hypothèses et décisions à confirmer »).
> Une ligne par décision ; on ne réécrit pas une décision, on en ajoute une
> nouvelle qui la remplace.

| ID | Date | Sujet | Décision | Justification |
|---|---|---|---|---|
| D-01 | 2026-11-16 | Réseau VirtualBox | Réutiliser le réseau hôte uniquement existant **`HostNetwork`** (`192.168.56.0/24`, plage `.1`–`.199`) ; VM en IP fixe `192.168.56.10`. | Déjà validé lors de tests précédents. Le chevauchement avec la plage DHCP est sans risque tant que `docflow-vm` est seule sur ce réseau. |
| D-02 | 2026-11-16 | Format d'entrée de l'OCR | **MS1 convertit tout document (PDF texte, PDF scanné, PNG, JPG) vers un format raster unique** avant l'OCR. La couche texte des PDF n'est **jamais** utilisée par la pipeline. | L'OCR doit recevoir la même chose quelle que soit la source. La couche texte des PDF Carrefour sert uniquement de **transcription de référence** pour mesurer le CER/WER. |
| D-03 | 2026-11-16 | Tickets papier | Le corpus actuel ne contient aucune photo de ticket papier. En attendant d'en collecter, le test T-02 (ticket incliné) utilise des **copies tournées/bruitées artificiellement**, uniquement hors jeu de test. | Respecter T-02 sans inventer de données réelles ; le rapport précisera qu'il s'agit d'une simulation. |
| D-04 | 2026-11-16 | Vérité de référence | Les annotations sont générées à partir des **noms de fichiers** (`<entite>_<AAAA>-<JJ>-<MM>_<montant>`), saisis à la main. La pipeline ne voit jamais le nom d'origine : fichier renommé en `document_id` à l'upload. | Éviter une fuite de la réponse vers l'extraction. |
| D-05 | 2026-11-16 | Messagerie (Q-01) | **RabbitMQ** confirmé : exchange topic `docflow.events`, files durables, file d'erreur. HTTP REST uniquement entre le client et l'API. | Découplage des étapes, messages conservés pendant une panne (T-07), tentatives et file d'erreur natives. |
| D-06 | 2026-11-16 | Base distribuée (Q-02) | **Pas de réplication ni de partitionnement en V1.** La répartition des données est : fichiers sur le Mac, résultats structurés sur Fedora. Présentée comme telle, sans parler de réplication. | Conforme au §7.3 ; une réplication sur la même machine physique n'apporterait pas de tolérance réelle. Extension possible si l'encadrant l'exige. |
| D-07 | 2026-11-16 | Accès à la base (Q-03) | Seuls **l'API** (compte `docflow_api` : lecture + création) et **MS3** (compte `docflow_ms3` : écriture) accèdent à PostgreSQL. MS3 tient aussi le **journal des étapes** en consommant tous les événements (`docflow.ms3.journal`). MS1 et MS2 n'ont aucun accès à la base. | Droits minimaux, un seul écrivain métier, statuts conservés même si MS3 est arrêté (les événements attendent en file). |
| D-08 | 2026-11-16 | Exécution de MS3 (Q-05) | Environnement virtuel Python + service **systemd** `docflow-ms3` sur Fedora, sans Docker. PostgreSQL natif Fedora. | Montre explicitement la combinaison conteneurs (Mac) + virtualisation (Fedora) du §1.2. |
| D-09 | 2026-11-16 | Événement supplémentaire | Ajout de `step.started` aux cinq événements du cahier. | Passage en `PROCESSING` et mesure du temps d'attente en file (§11.2). |
| D-10 | 2026-11-16 | Mode de secours | Profil Compose `noeud-b-local` : MS3 + PostgreSQL en conteneurs sur le Mac. | Développement et démonstration de secours si la VM ne démarre pas ; la cible reste le mode distribué. |
