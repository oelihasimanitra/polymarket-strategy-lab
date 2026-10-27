# Rapport A0 — correction A5-06 (chronologie JSON/SQL)

> **Mise à jour 2026-10-27 (post-audit A5).** Le validateur commun est
> désormais dans `src/polymarket_lab/validation/contracts.py` et la migration
> candidate `0007` aligne SQLite sur le contrat pour `end_time`. L'état courant
> est **717 collectés, 717 réussis, 0 xfail** après fermeture des
> contournements du writer.
> Voir `tests/REPORT_A0_CONTRACT_SQL_ALIGNMENT.md` et
> `tests/REPORT_A0_WRITER_VALIDATION_INTEGRATION.md`.

**Date :** 2026-10-27  
**Auteur :** A0 — architecte / intégrateur  
**Objet :** corriger l'incohérence de validation des périodes chronologiques
entre les contrats JSON et le schéma SQL, avant tout gel.  
**Statut :** correction appliquée au niveau contrats/tests. **Aucun commit,
aucun gel**, aucune migration `0005`/`0006` modifiée, aucune base réelle
ouverte en écriture.

## 1. Constat initial

Le SQL refusait déjà :

```text
fee_schedules   : effective_to IS NULL OR effective_to > effective_from
experiments     : end_time IS NULL OR end_time > start_time
```

Les schémas JSON validaient la forme des timestamps et la présence des champs,
mais pas l'ordre relatif de deux champs. Les deux tests A5-06 étaient donc des
`xfail(strict=True)` : ils décrivaient une divergence réelle entre validation
JSON et validation SQL.

Schémas concernés :

- `contracts/fee_schedule.schema.json` : `effective_from` / `effective_to` ;
- `contracts/experiment.schema.json` : `period.start_time` / `period.end_time`.

Contraintes SQL correspondantes :

- `schemas/initial_db_schema.sql` l. 178 (`fee_schedules`) ;
- `schemas/initial_db_schema.sql` l. 238 (`experiments`) ;
- les mêmes règles sont reprises dans `schemas/migrations/0004_consolidation.sql`
  l. 90 et 309.

## 2. Règle retenue

La règle n'est pas choisie arbitrairement : elle est celle déjà portée par le
SQL et par `ARCHITECTURE.md` §5.1.

- **Ordre strict** : `end_field > start_field`. Les bornes égales sont
  refusées. L'inclusivité n'est donc pas ambiguë : le SQL utilise `>`, pas
  `>=`.
- **Fin nulle** : autorisée lorsque le schéma l'autorise. La règle
  chronologique ne s'applique pas à une fin nulle.
- **Fin absente** :
  - `fee_schedule.effective_to` n'est pas requis : son absence est acceptée et
    équivaut à une période ouverte ;
  - `experiment.period.end_time` est requis : son absence est refusée, même
    pour `paper_live`. La valeur peut être `null` pour `paper_live`, mais la
    clé doit être présente.
- **Début** : `effective_from` et `start_time` sont requis et non nuls.
- **Type de période** : `research`, `validation` et `final_test` exigent déjà
  une fin non nulle dans le contrat JSON ; `paper_live` accepte `null`.
- **Format** : timestamps UTC canoniques
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`. La comparaison lexicographique est valide
  pour ce format. Les offsets (`+00:00`) et les fractions non conformes sont
  refusés par le motif JSON et par les `CHECK ... GLOB` SQL.

## 3. Pourquoi une extension et pas un mot-clé standard

JSON Schema 2020-12 ne fournit aucun opérateur standard comparant deux valeurs
d'instance. Il n'existe donc pas de `constraint` JSON Schema standard équivalent
à `effective_to > effective_from`.

Les deux schémas déclarent l'extension documentée :

```json
"x-polymarket-chronological-order": {
  "instance_path": [],
  "start_field": "effective_from",
  "end_field": "effective_to",
  "strict": true,
  "allow_null_end": true
}
```

et, pour `experiment`, avec `"instance_path": ["period"]`,
`"start_field": "start_time"`, `"end_field": "end_time"`.

Un `$comment` dans chaque schéma précise qu'un validateur JSON Schema standard
**ignore** cette extension. Le consommateur doit l'implémenter. Le point d'entrée
applicatif est `src/polymarket_lab/validation/contracts.py::validate_contract`
(schéma puis extension), utilisé par les tests de contrat et de parité.

Cette solution est explicite, mais elle n'est pas une validation JSON Schema
standard : c'est une limite documentée, pas un contournement silencieux.

## 4. Versionnement

`fee_schedule` passe de `1.1.0` à **`1.2.0`** pour ne pas modifier en place une
version auditée. `experiment` reste en `1.2.0`, déjà candidat non gelé. La
décision est consignée en **D-050** ; elle complète D-026 point 4 et D-049.

Aucune migration `0005`/`0006` n'a été modifiée : la règle chronologique SQL
existait déjà. Aucun gel n'est prononcé.

## 5. Fichiers modifiés

- `contracts/fee_schedule.schema.json` — extension chronologique, `$comment`,
  version `1.2.0` ;
- `contracts/experiment.schema.json` — extension chronologique, `$comment` ;
- `contracts/examples/fee_schedule.json` — `schema_version` `1.2.0` ;
- `contracts/README.md` — règle, extension, versionnement ;
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` — versions candidates et statistiques
  historisées/actualisées ;
- `ARCHITECTURE.md` — §5.1 et description du candidat `1.2.0` ;
- `DECISIONS.md` — D-050, mise à jour de D-026/D-049 ;
- `src/polymarket_lab/validation/contracts.py` — `validate_contract` et
  `chronology_errors` (point d'entrée applicatif) ;
- `tests/labtest/contracts.py` — réexport des conventions pour les tests ;
- `tests/unit/test_contracts_negative.py` — cas A5-06 ;
- `tests/unit/test_contracts_schema_validity.py` — déclaration de l'extension
  et version `fee_schedule` ;
- `tests/unit/test_contracts_examples.py` — version de l'exemple ;
- `tests/integration/test_contract_sql_parity.py` — parité JSON ↔ SQL des cas
  couverts ;
- `tests/README.md` — couverture et statistiques ;
- `tests/REPORT_A0_P0_REAUDIT_FIXES.md` — bannière historique A5-06 ;
- `tests/REPORT_A5_P0_FINAL_REAUDIT.md` — bannière historique A5-06 ;
- `tests/REPORT_A0_A5_06_FIX.md` — présent rapport.

## 6. Tests ajoutés ou convertis

Les deux tests `xfail(strict=True)` ont été **convertis**, pas supprimés :

- `test_fee_schedule_effective_period_must_be_ordered` ;
- `test_experiment_period_must_be_chronological`.

Cas couverts :

| Cas | `fee_schedule` | `experiment` |
|---|---|---|
| Période valide | accepté | accepté |
| Période inversée | refusé | refusé |
| Bornes égales | refusé | refusé |
| Fin nulle autorisée | accepté | accepté pour `paper_live` |
| Fin nulle interdite | — | refusé pour `research` |
| Fin absente | accepté (`effective_to` non requis) | refusé (`end_time` requis) |
| Début absent | refusé | refusé |
| Timestamp canonique | accepté | accepté |
| Offset `+00:00` | refusé | refusé |
| Format court `YYYY-MM-DD` | refusé | refusé |

La déclaration de l'extension est aussi vérifiée pour les deux schémas, et
chaque `schema_version` reste épinglée.

Parité JSON ↔ SQL (mêmes cas, insertion SQL réelle dans une base en mémoire) :

- `fee_schedule` : valide, inversé, égal, fin nulle, fin absente, format court ;
- `experiment` : valide, inversé, égal, fin nulle (`paper_live`), format court.

Résultats ciblés :

```text
tests/unit/test_contracts_negative.py
tests/unit/test_contracts_schema_validity.py
tests/integration/test_contract_sql_parity.py
→ 257 passed
```

## 7. Commandes et résultats

> **Chiffres historiques.** Les résultats `619` de cette section ont été
> mesurés avant `0007` et le writer. L'état courant est **717/717/0** ; voir
> `tests/REPORT_A0_WRITER_HARDENING_2.md`. Les résultats d'origine
> sont conservés ci-dessous.

Exécutées depuis la racine du dépôt avec `.\.venv\Scripts\python.exe` :

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
# 619 passed, 0 xfailed, 0 failed

.\.venv\Scripts\python.exe -m pytest tests --collect-only -q
# 619 tests collected

.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
# 619 passed, 0 failed

.\.venv\Scripts\python.exe -m pytest tests/integration/test_p0_candidates.py -q
# 55 passed
```

## 8. Sort des deux `xfail` A5-06

Les deux `xfail(strict=True)` ont disparu parce que leur cause est corrigée :

1. l'extension chronologique décrit la règle dans le schéma ;
2. `chronology_errors` l'applique ;
3. les deux tests vérifient désormais un refus réel, pas une anomalie
   attendue ;
4. `--runxfail` ne révèle plus aucun échec caché : **619 réussis, 0 échec**.

Aucun test n'a été supprimé, désactivé ou affaibli.

## 9. Réserve résiduelle découverte — présence de `end_time`

> **Traitement ultérieur :** cette réserve a été traitée par la migration
> candidate `0007` et les tests de parité 0.7. Voir
> `tests/REPORT_A0_CONTRACT_SQL_ALIGNMENT.md`. Le texte ci-dessous conserve
> l'état constaté à la date de ce rapport.

La correction A5-06 porte sur la comparaison `>`. Une divergence voisine
subsiste, hors du périmètre strict de la comparaison :

- le contrat JSON refuse `period.end_time = null` pour `research`,
  `validation` et `final_test` ;
- le SQL `experiments` accepte `end_time IS NULL` pour **tous** les
  `period_type`, car son `CHECK` ne teste que
  `end_time IS NULL OR end_time > start_time`.

Vérification exécutée sur une base en mémoire :

```text
SQL research + end_time NULL : ACCEPTÉ
```

Cette divergence n'a **pas** été corrigée dans `0005`/`0006`, conformément à la
consigne de signaler toute incohérence SQL réelle avant de la corriger. Elle
demande une décision du propriétaire : soit ajouter une contrainte SQL
(`period_type = 'paper_live' OR end_time IS NOT NULL`) dans une migration
dédiée, soit accepter explicitement que le SQL soit plus permissif que le
contrat. Tant que ce point n'est pas tranché, la parité JSON/SQL n'est pas
totale sur les champs nuls, même si la règle `>` de A5-06 est corrigée.

## 10. Limites et verdict

- Aucune base de travail réelle n'existe ; aucun test n'a été exécuté contre
  des données réelles.
- Aucune collecte, simulation, installation réseau, migration réelle, commit
  ou gel.
- L'extension n'est pas interprétée par un validateur JSON Schema standard :
  le point d'entrée `validate_contract` l'applique, mais aucun writer A1/A2
  n'existe encore pour l'appeler avant insertion. Voir
  `REPORT_A0_CONTRACT_SQL_ALIGNMENT.md`.
- **A5-06 (`>` strict) : corrigé et testé.**  
- **Parité des `end_time` NULL explicites : traitée par `0007` et testée sur
  0.7** ; la distinction clé absente / `NULL` reste une limite SQL documentée.
  Voir `REPORT_A0_CONTRACT_SQL_ALIGNMENT.md`. Le gel reste non prononcé.
