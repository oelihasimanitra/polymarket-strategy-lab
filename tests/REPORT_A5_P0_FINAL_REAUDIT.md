# Ré-audit final A5 — corrections P0 d'A0

> **Mise à jour A5-06 (2026-10-27).** Ce rapport est **historique** : il a été
> écrit avant la correction A5-06. Le constat `598 réussis, 2 xfail` et la
> réserve « A5-06 bloque le gel » ne sont plus l'état courant. A5-06 est traité
> par `tests/REPORT_A0_A5_06_FIX.md` et `0007` ; l'état courant est
> **672 réussis, 0 xfail** (writer durci, voir
> `tests/REPORT_A0_WRITER_HARDENING.md`). Le gel n'est pas prononcé.

**Date :** 2026-10-27  
**Agent :** A5 — Validation et benchmark  
**Objet :** vérification indépendante des corrections annoncées par A0 dans
`tests/REPORT_A0_P0_REAUDIT_FIXES.md`, après le ré-audit
`tests/REPORT_A5_P0_REAUDIT.md`.  
**Statut :** aucun gel, aucun commit, aucune migration sur une base de travail.
Toutes les bases utilisées sont en mémoire ou dans des répertoires temporaires
isolés.

## 1. Verdict global

**PASS pour les corrections P0 auditées.**

Les six points demandés sont vérifiés : provenance des conversions, tests de
portée/normalisation, runner `5→6`, conservation des neuf tables, cohérence des
rapports et absence de régression. L'audit indépendant a exécuté **97 contrôles,
tous PASS**.

Ce verdict ne vaut ni gel des contrats ni validation globale du projet. Deux
réserves restent explicites :

- **A5-06**, préexistante et hors du périmètre des corrections A0, reste
  matérialisée par les deux `xfail` de la suite ; elle bloque le gel
  contractuel tant qu'elle n'est pas tranchée ;
- les sondes manuelles 19/19, 13/13 et 4/4 sont documentées et leurs fichiers de
  résultats existent, mais elles n'ont pas été ré-exécutées indépendamment ;
  les comportements équivalents sont couverts par les tests automatisés et par
  l'audit ci-dessous.

## 2. Commandes réellement exécutées

Depuis la racine du dépôt :

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 598 passed, 2 xfailed, 0 failed
# 600 tests collectés (vérifié par --collect-only -q)

.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
# 55 passed

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 598 passed, 2 failed
# les deux échecs sont exactement les tests A5-06 attendus
```

Les deux `xfail`/échecs sous `--runxfail` sont :

- `test_fee_schedule_effective_period_must_be_ordered`
- `test_experiment_period_must_be_chronological`

Audit indépendant hors dépôt :

```powershell
.\.venv\Scripts\python.exe "$env:TEMP\a5_p0_final_audit.py"
# 97 PASS, 0 FAIL, 97 checks
```

Le script d'audit n'a pas été ajouté au dépôt. Il a utilisé `:memory:`, des
fichiers temporaires et une copie temporaire du dépôt pour le test de mutation.
Il n'a ouvert aucune base de travail en écriture.

## 3. Verdict par point demandé

| # | Point | Verdict | Preuves |
|---:|---|---|---|
| 1 | Provenance des conversions : `ref_type`, `ref_id`, `kind='settlement'` | **PASS** | Le préflight (`0006_p0_ledger.sql` l. 29-35), la dérivation (`MIN`, l. 176-184) et le trigger de provenance (l. 224-235) filtrent tous les trois `ref_type='market_resolution'`, `ref_id=resolution_event_id` et `kind='settlement'`. Les six cas demandés ont été rejoués sur bases temporaires. |
| 2 | Tests des triggers de remplacement : portée, normalisation, cas positif | **PASS** | Les six tests ajoutés couvrent quatre violations de portée, une violation de normalisation et un cas positif (`tests/integration/test_p0_candidates.py` l. 372-449). Le test de mutation confirme qu'ils échouent si les triggers sont retirés. |
| 3 | Runner réel `5→6` | **PASS** | Succès : sauvegarde, `user_version=6`, journal `[4,5,6]`, neuf comptages préservés, intégrité/FK, conversion rattachée. Échec préflight : restauration à 5, journal `[4,5]`, données, vues et table 0.5 intactes. Échec post-commit simulé : restauration identique. |
| 4 | Conservation des données sur les neuf tables | **PASS** | Audit indépendant sur une base 0.4 synthétique : les neuf comptages sont identiques avant 0005, après 0005 et après 0006. Les valeurs sont toutes non nulles. |
| 5 | Rapports et statistiques | **PASS** | `tests/README.md` donne 600/598/2 et 55 tests P0, et marque les campagnes antérieures comme historiques. `CONTRACT_FREEZE_PROPOSAL.md` distingue 472/470/2 (historique) de 600/598/2 (courant). Les sondes manuelles sont séparées des tests automatisés. Aucun gel n'est revendiqué. |
| 6 | Régression et A5-06 | **PASS** | 598 réussis, 2 xfail, 0 échec inattendu ; 55 tests P0, sans skip/xfail P0 ; `--runxfail` ne révèle que les deux A5-06. Aucune nouvelle régression. |

### 1. Provenance des conversions — détail

Les trois emplacements sont cohérents :

```sql
-- préflight
WHERE t.ref_type = 'market_resolution'
  AND t.ref_id = c.resolution_event_id
  AND t.kind = 'settlement'

-- dérivation
WHERE t.ref_type = 'market_resolution'
  AND t.ref_id = c.resolution_event_id
  AND t.kind = 'settlement'

-- trigger
WHERE t.experiment_id = NEW.experiment_id
  AND t.ref_type = 'market_resolution'
  AND t.ref_id = NEW.resolution_event_id
  AND t.kind = 'settlement'
```

Cas rejoués sur bases 0.5 temporaires :

| Cas | Résultat observé |
|---|---|
| Settlement valide | 0006 acceptée ; conversion rattachée à `exp_fixture_001`. |
| Adjustment seul | 0006 refusée (`CHECK constraint failed: bad = 0`) ; `user_version=5`, journal `[4,5]`, conversion et vues intactes. |
| Aucune transaction de ledger | 0006 refusée ; aucune perte de lignes. |
| Settlement dans une seule expérience | 0006 acceptée ; rattachement à cette expérience. |
| Settlement dans exp1 + adjustment dans exp2 | 0006 acceptée ; rattachement à exp1. Le trigger refuse ensuite une conversion pour exp2, qui n'a qu'un adjustment. |
| Plusieurs settlements, expériences différentes | 0006 refusée par le préflight, sans perte. |
| Plusieurs settlements, même expérience | 0006 refusée par la contrainte d'unicité reconstruite, sans perte. |

Chaque rejet a été contrôlé sur : `user_version` restant à 5, journal restant
`[4,5]`, neuf comptages inchangés, table `settlement_conversions` encore en
forme 0.5, vues restaurées, `integrity_check=ok` et `foreign_key_check` vide.

### 2. Tests de remplacement et test de mutation — détail

Le test de mutation a été exécuté sur une copie temporaire du dépôt :

| Configuration | Résultat |
|---|---|
| Migration 0005 intacte | 6 tests sélectionnés réussis. |
| `trg_event_replacements_scope` supprimé | 4 échecs, 2 réussis. Les quatre violations de portée ne sont plus rejetées. |
| `trg_event_replacements_normalizer` supprimé | 1 échec, 5 réussis. La violation de normalisation n'est plus rejetée. |

Cela confirme que les tests ne sont pas seulement présents : ils dépendent
effectivement des protections SQL. Le cas positif reste accepté dans les deux
mutations.

### 3. Runner `5→6` — détail

Le parcours réel `run_migration.apply_migration` a été exécuté sur des fichiers
temporaires :

- succès : sauvegarde créée, `user_version=6`, journal `[4,5,6]`,
  `integrity_check=ok`, `foreign_key_check` vide, conversion rattachée ;
- échec préflight sans settlement ou avec adjustment seul : sauvegarde
  restaurée, `user_version=5`, journal `[4,5]`, neuf comptages inchangés,
  table `settlement_conversions` sans `experiment_id`, vues restaurées ;
- échec post-commit simulé : restauration depuis la sauvegarde, mêmes contrôles
  d'intégrité et de comptages ;
- sauvegarde : `user_version=5`, journal `[4,5]`, neuf comptages identiques à
  la source.

### 4. Comptages des neuf tables — détail

Base synthétique 0.4 → 0.5 → 0.6, avec des lignes non nulles dans chaque table :

| Table | Avant 0005 | Après 0005 | Après 0006 |
|---|---:|---:|---:|
| `market_events` | 8 | 8 | 8 |
| `event_replacements` | 1 | 1 | 1 |
| `data_manifests` | 1 | 1 | 1 |
| `experiments` | 1 | 1 | 1 |
| `ledger_transactions` | 2 | 2 | 2 |
| `ledger_postings` | 5 | 5 | 5 |
| `settlement_conversions` | 1 | 1 | 1 |
| `simulated_orders` | 1 | 1 | 1 |
| `simulated_fills` | 2 | 2 | 2 |

Les valeurs absolues diffèrent du jeu A0 (deux expériences) mais la propriété
auditée est la conservation, pas la ressemblance du fixture.

**Observation de couverture :** le test automatisé 0005 ne compte pas les trois
tables du ledger, que 0005 ne reconstruit pas ; le test runner `5→6` compte les
neuf tables et l'audit indépendant les compte avant/après chaque migration.
Aucun risque de perte n'est identifié.

### 5. Rapports et statistiques — détail

- `tests/README.md` l. 9-10 : 600 collectés, 598 réussis, 2 xfail.
- `tests/README.md` l. 153-171 : anciennes campagnes marquées historiques ;
  tableau séparant sondes manuelles et tests automatisés.
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` l. 273-274 : 472/470/2 marqué
  historique, 600/598/2 courant.
- `tests/REPORT_A0_SQL_CORRECTIONS.md` l. 3 : bannière « RAPPORT HISTORIQUE ».
- `tests/REPORT_A5_P0_AUDIT.md` et `tests/REPORT_A5_P0_REAUDIT.md` : bannières
  historiques.
- `ARCHITECTURE.md` l. 573-579, `DECISIONS.md` D-045 et
  `schemas/migrations/README.md` l. 113-116 documentent la règle des trois
  conditions.
- Aucun document consulté ne revendique un gel ou une validation globale.

Les fichiers `probe_results.json`, `probe_0006_results.json` et
`recovery_results.json` du répertoire temporaire A0 totalisent respectivement
19, 13 et 4 entrées PASS. Leur ré-exécution indépendante n'a pas été faite ;
les scénarios correspondants sont couverts par les tests automatisés et par
l'audit indépendant.

### 6. Régression — détail

La suite complète reste à **598 réussis, 2 xfail, 0 échec inattendu**.
`--runxfail` produit exactement deux échecs, tous deux A5-06. Les 55 tests P0
passent, sans `skip` ni `xfail` P0. Le seul cas explicitement remplacé est
l'ancien test d'ambiguïté fondé sur un adjustment, remplacé par le cas correct
(settlement d'un côté, adjustment de l'autre), et l'ambiguïté réelle reste
couverte par le test de copie 0.5 volontairement corrompue. Le fichier de tests
étant non suivi par Git, l'historique exhaustif des suppressions n'est pas
vérifiable ; la couverture P0 est passée de 44 à 55 tests et aucun test P0
n'apparaît désactivé.

## 4. Anomalies restantes et points de vigilance

### A5-FINAL-01 — A5-06 reste ouverte — **Moyenne, préexistante, hors corrections P0**

Les deux tests A5-06 restent en `xfail` : les schémas JSON n'imposent pas
`effective_to > effective_from` pour un barème, ni `period.end_time >
period.start_time` pour une expérience, alors que le SQL l'impose. Ce n'est pas
une régression introduite par A0 et ce n'est pas bloquant pour les migrations
P0, mais c'est un point à trancher avant tout gel contractuel.

### A5-FINAL-02 — Couverture 0005 partielle sur les tables ledger — **Info**

Le test 0005 ne compte pas `ledger_transactions`, `ledger_postings` et
`settlement_conversions`. 0005 ne reconstruit pas ces tables, et le test
runner `5→6` ainsi que l'audit indépendant couvrent les neuf tables. Aucun
défaut de comportement.

### A5-FINAL-03 — Sondes manuelles non ré-exécutées — **Info / NON VÉRIFIÉ**

Les résultats 19/19, 13/13 et 4/4 sont documentés et leurs JSON existent, mais
A5 ne les a pas rejoués indépendamment pour ne pas modifier les preuves A0. Les
mêmes invariants sont couverts par la suite automatisée (55 tests P0) et par
les 97 contrôles indépendants.

### A5-FINAL-04 — Formulation « les deux conversions » dans le rapport A0 — **Info**

Le rapport A0 mentionne « les deux conversions » dans le scénario
settlement + adjustment, alors que le test automatisé correspondant n'insère
qu'une conversion. Le comportement vérifié (rattachement au settlement,
rejet du trigger pour l'expérience sans settlement) est correct ; il s'agit
d'une imprécision rédactionnelle, pas d'un défaut de migration.

### A5-FINAL-05 — Historique des tests non vérifiable — **Info / NON VÉRIFIÉ**

Le rapport A0 affirme qu'aucun test existant n'a été supprimé, tout en
indiquant qu'un ancien test d'ambiguïté a été remplacé. Le fichier
`tests/integration/test_p0_candidates.py` n'est pas suivi par Git dans l'état
actuel, donc la comparaison exacte des noms de tests avant/après n'est pas
possible. La couverture a augmenté (44 → 55 tests P0), aucun `skip`/`xfail`
P0 n'est présent, et les scénarios critiques sont couverts ; la formulation du
rapport A0 reste toutefois ambiguë.

## 5. Recommandation explicite

**J'autorise la prochaine étape de développement P0** (poursuite de
l'intégration et des travaux A1/A2) dans l'état actuel : les corrections
demandées sont effectives, les migrations s'exécutent et se restaurent
correctement sur bases temporaires, les neuf comptages sont conservés et aucune
régression n'est constatée.

**Je n'autorise pas le gel des contrats ni la présentation des migrations
`0005`/`0006` comme approuvées ou gelées.** Conditions restantes :

1. trancher A5-06 (validation contractuelle ou acceptation explicite et
   documentée de la limite) avant le gel ;
2. conserver la distinction entre tests automatisés et sondes manuelles ;
3. ne pas committer les migrations candidates comme définitives sans
   l'autorisation du propriétaire.

Aucun gel n'est prononcé. Aucun commit n'est créé. Aucune base de travail réelle
n'a été ouverte en écriture : aucun fichier `.db`/`.sqlite`/`.sqlite3` n'existe
dans le dépôt, `data/` ne contient que `.gitkeep`, et toutes les opérations de
ce ré-audit ont porté sur `:memory:` ou des copies temporaires.
