# Audit A5 indépendant — migrations P0 `0005` et `0006`

> **RAPPORT HISTORIQUE.** Cet audit précède les corrections A5-REAUDIT. Ses
> chiffres (`586/2`, 43 tests P0) ne sont pas l'état courant. Voir
> `tests/REPORT_A5_P0_REAUDIT.md` puis
> `tests/REPORT_A0_P0_REAUDIT_FIXES.md`.

**Date :** 2026-10-27  
**Agent :** A5 — Validation et benchmark  
**Objet :** vérification indépendante des migrations candidates
`0005_p0_foundations.sql` (0.4 → 0.5) et `0006_p0_ledger.sql` (0.5 → 0.6).  
**Statut :** aucun gel, aucun commit, aucune migration exécutée sur la base de
travail.

## Méthode

- lecture du rapport A0 disponible dans le dépôt
  (`tests/REPORT_A0_SQL_CORRECTIONS.md`), des migrations `0005`/`0006`, du
  runner `run_migration.py`, de `ARCHITECTURE.md`, de `DECISIONS.md` et des
  tests P0 ;
- exécution de la suite complète et des tests ciblés **sur des bases en
  mémoire ou temporaires** ; aucune migration n'a été appliquée à une base de
  travail, qui n'existe d'ailleurs pas dans le dépôt ;
- inspection statique des triggers, index, vues et préflights ;
- aucune modification de code, de contrat ou de base. Seul ce rapport est
  ajouté.

Commandes exécutées :

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
.\.venv\Scripts\python.exe -m pytest tests\integration\test_consolidation_0004.py -q
.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
```

Résultats :

- suite complète : **586 réussis, 2 xfail, 0 échec** ;
- `test_p0_candidates.py` : **43 réussis** ;
- `test_consolidation_0004.py` : **20 réussis** ;
- `--runxfail` : **586 réussis, 2 échoués** — les deux échecs sont les tests
  A5-06 déjà documentés, aucun test P0.

## Verdict par point

| # | Point audité | Verdict | Preuve et réserve |
|---:|---|---|---|
| 1 | Base originale non modifiée | **PARTIEL** | Aucun fichier `.db`/`.sqlite` dans le dépôt ; `data/` ne contient que `.gitkeep` ; aucun fichier de base dans l'historique Git ; les tests P0 utilisent `:memory:`/`tmp_path` et le README des migrations interdit l'application à la base de travail. **Réserve :** aucun chemin, hash ou comptage de « base originale » n'est fourni par A0 ; l'absence de modification est donc constatée par absence d'artefact, pas par comparaison avant/après. |
| 2 | Ordre des migrations | **PASS** | Registre du runner : `3→0004`, `4→0005`, `5→0006` (`run_migration.py` l. 43-62). `schema_06` applique `0004`, puis `0005`, puis `0006`. Le test 0005 vérifie le journal `[4, 5]` ; 0006 écrit `user_version = 6` et la ligne `(6, '0006_p0_ledger')`. **Réserve :** aucun test n'exerce le runner de fichier sur le chemin `5→0006`, et le journal `[4, 5, 6]` n'est pas asserté après 0006. Le SQL 0006 ne vérifie pas lui-même `user_version = 5` ; c'est le runner qui le fait. |
| 3 | Intégrité SQLite et clés étrangères | **PASS** | `test_0005_applies_to_04_and_preserves_legacy_rows` vérifie `integrity_check = ok` et `foreign_key_check` vide après 0005. `test_0006_applies_and_keeps_rows` fait de même après 0006. Le runner refait ces contrôles après chaque migration. |
| 4 | Comptages des tables reconstruites | **PARTIEL** | Le SQL copie les lignes sans filtre (`INSERT ... SELECT`), donc la préservation est correcte par construction. Les tests ne comptent cependant que `market_events`, `experiments` et `data_manifests` en 0005, et ne comptent pas `event_replacements`. Pour 0006, le test vérifie la présence d'une transaction et d'une conversion, pas les comptages de `ledger_transactions`, `ledger_postings` et `settlement_conversions`. Le contrôle de comptage du runner n'est pas exercé sur `5→0006`. Aucun comptage brut avant/après n'est fourni par A0. |
| 5 | Identité v2 et chaînes de remplacement | **PASS** | Triggers `trg_market_events_identity_v2`, `anchor_v2`, `shape_v2` ; index v1/v2 et repli payload. Tests : unicité source par type/normalizer, anchor obligatoire, repli raw, vecteurs `event_id/v2`, exemples recalculés. Chaînes : monotonie, cycles, `visible_from`, `created_at`, append-only, `INSERT OR REPLACE`, horloge injectée. **Réserves de couverture :** les triggers `trg_event_replacements_scope` (même source/type/marché/token) et `trg_event_replacements_normalizer` sont inspectés statiquement mais pas directement testés. Le SQL ne peut pas recalculer le SHA-256 de `event_id` ; la recette exacte reste vérifiée par les vecteurs d'exemple, pas à l'insertion. |
| 6 | Manifestes non scellés inaccessibles en as-of | **PASS** | `v_manifest_event_visibility` joint `manifest_seals` ; `test_unsealed_manifest_is_not_visible` obtient 0 ligne. Les listes et le seal sont append-only, les collisions `INSERT OR REPLACE` sont refusées même avec `recursive_triggers=OFF`, et le seal vérifie hash/comptages. **Limite C-03 documentée :** les tables brutes restent lisibles par un `SELECT` privilégié. |
| 7 | Unicité du ledger par expérience | **PASS** | 0006 ajoute `UNIQUE(experiment_id, ref_type, ref_id, kind)` et `UNIQUE(experiment_id, idempotency_key)`. `test_ledger_uniqueness_is_scoped_per_experiment` autorise les mêmes clés dans deux expériences, refuse les doublons dans une même expérience et vérifie l'immuabilité UPDATE/DELETE. |
| 8 | Conversions de règlement rattachées à une expérience | **PASS** | 0006 impose `experiment_id NOT NULL`, FK, unicité par expérience et trigger de provenance. Les tests couvrent l'absence de contexte, l'ambiguïté inter-expériences, le doublon dans une expérience, l'expérience étrangère et l'immuabilité. **Observation :** le préflight dérive l'expérience de toute transaction `ref_type='market_resolution'`, sans exiger `kind='settlement'` ; cela n'a pas produit d'ambiguité dans les tests, mais mérite d'être documenté. |
| 9 | Tests de régression et P0 | **PASS** | 586 réussis, 2 xfail, 0 échec. Les 43 tests P0 et les 20 tests de consolidation 0004 passent. `--runxfail` ne révèle que les 2 échecs A5-06 attendus. |
| 10 | Limites C-02 et C-03 documentées | **PASS** | C-02 : `ARCHITECTURE.md` invariant 22, D-047, `tests/README.md` l. 141-145 ; tests d'horloge injectée et de refus d'antidatage. C-03 : invariant 23, D-048, README l. 146-148 ; test du manifeste non scellé. Les limites (horloge murale non prouvable en SQL direct ; tables brutes lisibles) sont explicites. |

Bilan : **8 PASS, 2 PARTIEL, 0 FAIL**.

## Divergences avec les artefacts d'A0

1. **Rapport A0 incomplet pour P0.** Le seul rapport A0 présent,
   `tests/REPORT_A0_SQL_CORRECTIONS.md`, couvre la correction 0.3 et les
   anomalies A5-01 à A5-24. Il ne documente ni les migrations `0005`/`0006`, ni
   leurs comptages, ni les résultats P0. Les affirmations P0 sont dans
   `tests/README.md` et `schemas/migrations/README.md`, pas dans un rapport A0
   dédié. L'audit ne peut donc pas comparer ses résultats à un rapport A0 P0
   inexistant.
2. **Comptage de tests périmé.** Le rapport A0 indique `472 collectés,
   470 réussis, 2 xfail` (l. 32-35) ; `CONTRACT_FREEZE_PROPOSAL.md` reprend
   `472/470/2` (l. 273). L'exécution actuelle donne **588 collectés, 586
   réussis, 2 xfail**. L'écart s'explique par l'ajout des tests P0, mais les
   deux documents ne sont pas à jour. `tests/README.md` est, lui, à jour.
3. **« 48 PASS, 3 PARTIEL, 0 FAIL ».** Cette phrase de `tests/README.md`
   (l. 149-152) n'est adossée à aucun rapport visible. Notre audit retrouve
   bien 0 FAIL, mais classe **1 et 4** en PARTIEL pour absence de base de
   comparaison et insuffisance des assertions de comptage. Nous ne retrouvons
   pas la répartition exacte annoncée.
4. **Comptages « cohérents ».** A0/README l'affirment ; les tests ne couvrent
   pas tous les comptages (point 4). La préservation est correcte par lecture
   du SQL, mais la preuve automatisée est partielle.
5. **Résultats A0 vs A5 sur les xfail.** A0 rapporte 2 xfail A5-06 ; c'est
   confirmé. Aucun xfail P0 n'est masqué.

## Constats supplémentaires

- Le runner de fichiers n'est testé que sur `4→0005`. Le chemin `5→0006`, la
  sauvegarde/restauration et le contrôle de comptage associé ne sont pas
  exercés par un test dédié.
- Le test `test_0006_applies_and_keeps_rows` ne vérifie pas les comptages
  avant/après des trois tables reconstruites ; il vérifie seulement qu'une
  transaction et une conversion restent présentes.
- `trg_event_replacements_scope` et `trg_event_replacements_normalizer` ne sont
  pas couverts par un test négatif.
- Le SQL ne peut pas vérifier que `event_id` est bien le SHA-256 tronqué de la
  recette v2 ; cette vérification reste applicative. Les vecteurs d'exemple la
  couvrent, pas les insertions SQL.
- Le préflight 0006 accepte toute transaction `ref_type='market_resolution'`
  pour déduire l'expérience, sans filtrer sur `kind='settlement'`. À documenter
  ou à durcir si A2 peut produire d'autres transactions sur la même référence.
- Aucun fichier de base original n'existe dans le dépôt : la vérification du
  point 1 est donc une vérification d'absence, pas une comparaison de hash.

## Conclusion

Les migrations `0005` et `0006` sont cohérentes avec les règles C-01, C-02 et
C-03 telles que documentées, et la suite de régression/P0 passe. Les deux
réserves principales sont l'absence de preuve de non-modification d'une base
originale (point 1) et l'insuffisance des assertions de comptage après
reconstruction (point 4). Aucun FAIL n'est constaté.

**Aucun gel n'est prononcé. Aucun commit n'est créé.**
