# Ré-audit A5 indépendant — dry-run P0 `0005` / `0006`

> **RAPPORT HISTORIQUE.** Ce ré-audit décrit l'état **avant** les corrections
> A5-REAUDIT-01 à -04. Ses chiffres (`587/2`, 44 tests P0, verdict PARTIAL) ne
> sont pas l'état courant. Voir `tests/REPORT_A0_P0_REAUDIT_FIXES.md`.

**Date :** 2026-10-27  
**Agent :** A5 — Validation et benchmark  
**Objet :** vérification indépendante du dry-run synthétique annoncé par A0
après les corrections P0.  
**Statut :** aucun gel, aucun commit, aucune migration sur une base réelle.

## 1. Verdict global

**PARTIAL.**

Les migrations s'exécutent correctement sur des copies temporaires, les
comptages des tables reconstruites sont préservés, le runner `5→0006` fonctionne
et restaure la sauvegarde en cas d'échec, et les triggers de portée/normalisation
sont efficaces. Deux réserves empêchent un verdict PASS :

1. le préflight et le trigger de provenance des conversions ne filtrent pas
   `kind='settlement'` ; une transaction `adjustment` seule suffit à rattacher
   une conversion à une expérience (anomalie A5-REAUDIT-01) ;
2. les rapports/README contiennent encore des statistiques obsolètes et des
   verdicts non étayés (anomalie A5-REAUDIT-04).

Aucune régression logicielle n'a été constatée.

## 2. Commandes exécutées et résultats

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 589 collectés, 587 réussis, 2 xfail (A5-06), 0 échec

.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
# 44 réussis

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 587 réussis, 2 échoués : uniquement les 2 tests A5-06
```

Audit indépendant sur bases en mémoire et fichiers temporaires :
**64 contrôles PASS, 0 FAIL**. Le script d'audit n'a pas été ajouté au dépôt ;
il n'a utilisé que `:memory:` et `tempfile.TemporaryDirectory()`. Aucun fichier
de base n'existe dans le dépôt, `data/` ne contient que `.gitkeep`, et aucune
base de travail n'a été ouverte en écriture.

## 3. Verdict par vérification demandée

| # | Vérification | Verdict | Preuves |
|---:|---|---|---|
| 1 | Tests rapportés vs tests réellement exécutés | **PASS** | `pytest tests -q -rxX` : 589 collectés, 587 réussis, 2 xfail, 0 échec. Les 2 xfail sont exactement `test_fee_schedule_effective_period_must_be_ordered` et `test_experiment_period_must_be_chronological` (A5-06). `--runxfail` donne 587 réussis et ces 2 seuls échoués. `test_p0_candidates.py` : 44 réussis. |
| 2 | Comptages avant/après de toutes les tables reconstruites | **PASS** | Audit indépendant : 0005, `event_replacements` 1 → 1, plus `market_events` 2 → 2, `data_manifests` 1 → 1, `experiments` 1 → 1, `fee_schedules`/`hypotheses`/`strategies` 1 → 1. 0006, `ledger_transactions` 2 → 2, `ledger_postings` 5 → 5, `settlement_conversions` 1 → 1, `event_replacements` 0 → 0. **Écart de couverture A0 :** ses tests ne comptent que 3 tables en 0005 et ne comptent pas les tables reconstruites en 0006. |
| 3 | Parcours réel `run_migration.py` 5 → 6 | **PASS** | Base fichier temporaire 0.5, `runner.apply_migration(path)` sélectionne 0006. Vérifié : sauvegarde créée, `user_version=6`, journal `[4,5,6]`, comptages préservés, `integrity_check=ok`, `foreign_key_check` vide, conversion rattachée. Sauvegarde à `user_version=5`, journal `[4,5]`, comptages préservés. Échec préflight sans contexte : restauration à 5, journal `[4,5]`, données intactes, table 0.5 non remplacée. Échec **post-commit** simulé : restauration effective à 5, journal `[4,5]`, données et table 0.5 restaurées. |
| 4 | Tests négatifs des triggers de portée et de normalisation `event_replacements` | **PARTIAL** | **Aucun test A0** ne couvre `trg_event_replacements_scope` ni `trg_event_replacements_normalizer`. Audit indépendant : 4/4 rejets vérifiés (source différente, type différent, marché/token différents, normalizer différent) avec les messages attendus, et acceptation d'un remplacement de même portée. Le comportement est correct ; la couverture A0 manque. |
| 5 | Préflight des conversions : règlement valide vs autres transactions | **PARTIAL** | Cas valide `kind='settlement'` accepté. Cas sans ledger et cas ambigu inter-expériences rejetés sans perte de lignes (`user_version` reste 5, journal `[4,5]`, comptages inchangés, intégrité/FK OK). **Mais** une transaction `kind='adjustment'` seule, avec `ref_type='market_resolution'`, est acceptée et la conversion est rattachée à cette expérience. Le préflight (l. 30-34), la dérivation `MIN` (l. 180) et le trigger de provenance (l. 222-231) ne filtrent pas `kind='settlement'`. |
| 6 | Absence de statistiques obsolètes / verdicts non étayés | **FAIL** | `tests/README.md` : 589/587/2 en tête (l. 9-10) mais 586 réussis/2 xfail en pied (l. 152), et « 48 PASS, 3 PARTIEL, 0 FAIL » (l. 149) n'est adossé à aucun rapport. `contracts/CONTRACT_FREEZE_PROPOSAL.md` l. 273 indique encore 472/470/2. `tests/REPORT_A0_SQL_CORRECTIONS.md` l. 32-34 indique 472/470/2 et 137/2. Les chiffres 19/19, 13/13 et 4/4 annoncés ne sont détaillés dans aucun rapport du dépôt. |
| 7 | Documentation des limites C-02 et C-03 | **PASS** | C-02 : `ARCHITECTURE.md` invariant 22, D-047, `tests/README.md` l. 141-145 ; limite explicite sur l'horloge murale non prouvable en SQL direct. C-03 : invariant 23, D-048, README l. 146-148 ; limite explicite sur la lecture directe des tables brutes. |
| 8 | Régression introduite par les dernières corrections | **PASS** | Suite complète 587 réussis / 2 xfail / 0 échec ; `--runxfail` ne révèle que les 2 A5-06 ; 44 tests P0 passent ; 64 contrôles indépendants passent. Aucune régression fonctionnelle constatée. |

Bilan : **5 PASS, 2 PARTIAL, 1 FAIL**.

## 4. Anomalies restantes

### A5-REAUDIT-01 — Provenance des conversions non filtrée sur `kind='settlement'` — **Moyenne**

**Constat.** Le préflight 0006 compte les expériences distinctes parmi toutes
les transactions `ref_type='market_resolution'`, sans condition sur `kind`
(`0006_p0_ledger.sql` l. 30-34). La dérivation `MIN(experiment_id)` (l. 180) et
le trigger `trg_settlement_conversions_provenance` (l. 222-231) utilisent la
même condition large.

**Preuve indépendante.** Sur une base 0.5 temporaire, une conversion et une
seule transaction `kind='adjustment', ref_type='market_resolution'` : 0006 est
accepté et la conversion est rattachée à l'expérience de l'ajustement. Le
message du trigger parle pourtant de « transaction de settlement ».

**Conséquence.** Une conversion peut être rattachée à une expérience qui n'a
pas de settlement, si un ajustement ou une autre transaction de résolution y
existe. Le cas ambigu inter-expériences est bien rejeté, mais le cas
« adjustment seul » ne l'est pas.

**Correction proposée.** Ajouter `AND t.kind = 'settlement'` aux trois endroits,
ou documenter explicitement que `ref_type='market_resolution'` est le critère
de provenance et ajouter un test qui fige cette règle. Si les reversals de
settlement doivent compter, autoriser `kind IN ('settlement', 'reversal')` et le
documenter.

### A5-REAUDIT-02 — Pas de tests A0 pour la portée/normalisation des remplacements — **Faible**

Les triggers `trg_event_replacements_scope` et
`trg_event_replacements_normalizer` sont présents et efficaces (4/4 cas
négatifs vérifiés indépendamment), mais aucun test de `test_p0_candidates.py` ne
les exerce. Ajouter quatre tests négatifs et un test positif.

### A5-REAUDIT-03 — Couverture A0 incomplète du runner et des comptages — **Faible**

A0 teste le runner `4→0005` mais pas `5→0006`, et ne compte pas toutes les
tables reconstruites. L'audit indépendant comble ces trous, mais la suite
committée ne les protège pas contre une régression. Ajouter :

- un test runner `5→0006` avec journal `[4,5,6]` et sauvegarde à 5 ;
- un test d'échec post-commit avec restauration ;
- des comptages avant/après pour `event_replacements`, `ledger_transactions`,
  `ledger_postings` et `settlement_conversions`.

### A5-REAUDIT-04 — Statistiques et verdicts obsolètes — **Moyenne**

- `tests/README.md` l. 9-10 (589/587/2) et l. 149-152 (48 PASS, 3 PARTIEL,
  586/2) se contredisent.
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` l. 273 : 472/470/2.
- `tests/REPORT_A0_SQL_CORRECTIONS.md` l. 32-34 : 472/470/2 et 137/2, sans
  mention « historique ».
- Les chiffres 19/19 C-01/C-02/C-03, 13/13 contraintes 0006 et 4/4 récupération
  ne sont détaillés dans aucun rapport du dépôt.
- `tests/REPORT_A5_P0_AUDIT.md` (audit précédent) indique 586/2 et est supersédé
  par le présent ré-audit ; il devrait être marqué historique.

**Correction proposée.** Mettre à jour les chiffres ou marquer explicitement
les rapports datés comme historiques ; ajouter un tableau de vérification
19/13/4 avec les noms de tests ou d'assertions.

### A5-REAUDIT-05 — Absence de base originale à comparer — **Info**

Aucun fichier `.db`/`.sqlite` n'existe dans le dépôt ou dans `data/` ; aucun
fichier de base n'est suivi par Git. L'absence de modification d'une base réelle
est donc confirmée par absence d'artefact et par l'usage exclusif de bases
temporaires, pas par un hash avant/après. Ce n'est pas un défaut du dry-run,
mais une limite de preuve à mentionner.

## 5. Recommandation

**Ne pas autoriser le passage à la prochaine étape en l'état.**

Le socle est techniquement solide : migrations exécutables, comptages
préservés, runner et restauration vérifiés, triggers de remplacement efficaces,
aucune régression. Mais A5-REAUDIT-01 est une ambiguïté sémantique sur le
rattachement des conversions, et A5-REAUDIT-04 laisse des rapports
contradictoires. Conditions de passage :

1. A0 tranche A5-REAUDIT-01 : filtre `kind='settlement'` (ou règle élargie
   documentée et testée) ;
2. A0 met à jour ou archive les statistiques obsolètes et détaille les
   vérifications 19/13/4 ;
3. A0 ajoute les tests manquants du runner `5→0006`, des comptages et des
   triggers de portée/normalisation ;
4. A5 relance la suite et ce ré-audit après corrections.

Aucun gel n'est prononcé. Aucun commit n'est créé. Aucune migration n'a été
exécutée sur une base réelle ; toutes les migrations de ce ré-audit ont été
appliquées à des bases en mémoire ou à des copies temporaires isolées.
