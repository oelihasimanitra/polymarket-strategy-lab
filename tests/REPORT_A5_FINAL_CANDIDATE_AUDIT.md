# Rapport A5 — audit indépendant final des corrections du writer

**Date :** 2026-10-27  
**Auditeur :** A5 — auditeur technique indépendant  
**Objet audité :** `tests/REPORT_A0_FINAL_CANDIDATE_FIXES.md` et les corrections
A5-C2-01 à A5-C2-04 du writer de contrats.  
**Statut du writer :** **candidat non approuvé**. Aucun gel, aucune approbation
de production, aucun commit, aucune intégration A1/A2, aucune collecte, aucune
simulation, aucune base réelle.

## 1. Verdict général

**Verdict : PARTIAL.**

Les quatre corrections demandées sont **démontrées et PASS dans leur
périmètre** :

- `multipleOf` est refusé à la construction, avec défense secondaire à
  l'exécution ;
- les `$ref` locales sont vérifiées à la construction : cible existante, cible
  objet, validité structurelle, absence de cycle ;
- `ContractSchemaUnreadableError` et `ContractSchemaMismatchError` sont
  effectivement produites, normalisées en `ContractApprovalError`, avec chaîne
  de causes et sans ligne ;
- l'ordre réel est validation initiale → `BEGIN IMMEDIATE` → vérification
  finale → INSERT → relecture → COMMIT/ROLLBACK, et un échec final annule la
  transaction.

Aucun défaut bloquant n'a été trouvé dans ces corrections. Le verdict reste
**PARTIAL** et non **PASS** parce que le candidat conserve des conditions
importantes non démontrées ou non tranchées : choix A/B du validateur de
production, absence de tests de concurrence/crash/reprise, fenêtre TOCTOU
résiduelle, permissions réelles non testées, migrations non suivies par Git,
parcours de test importable et intégration A1/A2 inexistante. Ces points
empêchent une approbation de production, pas la validation des corrections
finales.

**Recommandation :** accepter les corrections finales comme closes dans le
périmètre audité, maintenir le writer **candidat**, ne pas geler les contrats,
ne pas l'intégrer en production, et traiter les conditions du § 7 avant toute
décision d'exploitation locale ou de production.

## 2. Périmètre, méthode et nature des preuves

### 2.1 Contrôles demandés

| Audit | Objet |
|---|---|
| A | `multipleOf` : refus à la construction, fail-closed, classification, absence d'insertion, cas décimaux/limites, chemins alternatifs, schémas approuvés |
| B | `$ref` : locales uniquement, cibles existantes/objets schéma, cycles à la construction, cibles externes/invalides, erreurs non différées, absence de ligne, récursion documentée |
| C | `ContractSchemaUnreadableError` et `ContractSchemaMismatchError` : production directe, causes, catégories, transaction, absence de ligne |
| D | Ordre réel validation → `BEGIN IMMEDIATE` → relecture finale → INSERT → commit/rollback ; absence de ligne partielle ; pas de revendication de concurrence |
| E | Non-régression : suite complète, collecte, `--runxfail`, writer/validateur, connexion, manifeste, `git diff --check`, pas de test supprimé/affaibli |
| F | Traçabilité : fichiers modifiés/non suivis, migrations, cohérence rapport/code/tests, absence de modification non autorisée |

### 2.2 Nature des preuves

- **Exécuté :** suite complète et sous-ensembles, scripts indépendants de
  sondage du validateur, sondage indépendant de la vérification finale
  illisible, vérification des hashes de migration, commandes Git.
- **Inspection :** ordre des appels, chaînes de causes, exports, absence
  d'import A1/A2, contenu des tests, documentation.
- **Documentaire :** décisions A/B, limites TOCTOU/concurrence, statut du gel,
  baseline de migration.
- **Non testé :** concurrence multi-connexions, crash/reprise, permission
  Windows réellement refusée, packaging installé hors dépôt, conformité JSON
  Schema exhaustive, writer A1/A2 réel, collecte/simulation/base réelle.

A5 n'a modifié aucun fichier de production, aucun test, aucune migration et
n'a prononcé aucun gel. Les scripts de sondage ont été exécutés hors du dépôt,
dans `%TEMP%`; la base utilisée pour le sondage final est une base SQLite
**en mémoire**, pas une base de travail réelle.

## 3. Résultats par contrôle

### 3.1 Audit A — `multipleOf`

| ID | Contrôle | Preuve | Résultat |
|---|---|---|---|
| A-01 | Refus à la construction, y compris décimales et limites | tests A0 + sondage indépendant | **PASS** |
| A-02 | Message explicite et type `UnsupportedSchemaError` | test + inspection `schema_validator.py:233-237` | **PASS** |
| A-03 | Absence de `multipleOf` dans le sous-ensemble scalaire | inspection de `_SCALAR_KEYWORDS` et de `_validate_schema_node` | **PASS** |
| A-04 | Refus dans les sous-schémas (`properties`, `$defs`, `allOf`, `anyOf`, `oneOf`, `items`, `additionalProperties`, `if/then/else`) | sondage indépendant | **PASS** |
| A-05 | Refus dans une cible `$ref`, y compris une cible sous annotation atteinte par `$ref` | sondage indépendant | **PASS** |
| A-06 | Refus après injection en mémoire | test A0 racine + sondage indépendant racine et imbriqué | **PASS** |
| A-07 | Aucun schéma approuvé `experiment`/`fee_schedule` n'utilise `multipleOf` | test A0 + parcours récursif indépendant des clés | **PASS** |
| A-08 | Schéma approuvé invalide contenant `multipleOf` : `ContractApprovalError`, cause `UnsupportedSchemaError`, aucune ligne | test A0 + `ContractSpec.from_approved` indépendant | **PASS** |
| A-09 | Chemin normal du writer sans paramètre de schéma/validateur | inspection des signatures publiques | **PASS** |

Détails exécutés :

- valeurs refusées à la construction : `0.1`, `0.3`,
  `0.30000000000000004`, `1`, `2`, `-1`, `0`, `1e-12`, `1e308` ;
- refus dans les sous-schémas et dans une cible `$ref` ;
- refus de la variante de casse `multipleof` comme mot-clé inconnu ;
- `ContractSpec.from_approved` sur un schéma approuvé temporaire contenant
  `multipleOf` : `ContractApprovalError` avec
  `__cause__ == UnsupportedSchemaError` ;
- aucun des deux schémas approuvés ne contient la clé `multipleOf`.

**Limites / chemins alternatifs :**

- Le module **test-only** `contract_writer_testing` accepte un validateur
  fourni (`Draft202012Validator` par exemple) et peut donc valider un schéma
  contenant `multipleOf`. Ce module n'est pas exporté par
  `polymarket_lab.storage` et n'est pas le writer normal. C'est une limite
  explicite, pas une preuve que le writer normal l'accepte.
- Le helper générique `validate_contract` accepte aussi un validateur fourni
  par l'appelant, par conception. Il ne réalise aucune écriture et ne constitue
  pas le chemin d'approbation du writer.
- Un `INSERT` SQL direct contourne le writer ; ce point reste documenté.

### 3.2 Audit B — `$ref`

| ID | Contrôle | Preuve | Résultat |
|---|---|---|---|
| B-01 | Seules les références locales `#/...` sont acceptées | inspection + tests + sondage | **PASS** |
| B-02 | Une cible inexistante est refusée | test A0 + sondage | **PASS** |
| B-03 | Une cible non-objet (`string`, `list`, `bool`, `null`) est refusée | test A0 + sondage | **PASS** |
| B-04 | Une cible objet est validée structurellement à la construction | inspection + test cible avec mot-clé inconnu | **PASS** |
| B-05 | Les cycles directs, mutuels et via `properties`, `allOf`, `anyOf`, `oneOf`, `if/then/else`, `items`, `additionalProperties` sont refusés | test A0 + sondage indépendant | **PASS** |
| B-06 | Les références distantes (`https`, `file`) sont refusées | test A0 + sondage | **PASS** |
| B-07 | Une erreur de référence d'un schéma approuvé est refusée avant insertion, sans ligne | test A0 + `ContractSpec.from_approved` indépendant | **PASS** |
| B-08 | Les schémas récursifs valides sont refusés et la limitation est documentée | inspection, `WRITER_INTEGRATION.md`, `DECISIONS.md` D-055 | **PASS (limite documentée)** |
| B-09 | Les références valides (`$defs`, `properties`, chaîne, réutilisation, sibling, échappements `~0`/`~1`) sont acceptées | sondage indépendant | **PASS** |
| B-10 | Validation stricte du pointeur JSON | sondage indépendant | **ÉCART FAIBLE** (voir A5-FC-01) |

Le sondage indépendant global a exécuté 60 contrôles, dont les contrôles B
suivants :

- 9 familles de références valides acceptées et appliquées au document ;
- 22 familles de références invalides/cycliques refusées ;
- 2 schémas approuvés invalides refusés via `ContractSpec.from_approved` avec
  cause `UnsupportedSchemaError`.

Les deux schémas approuvés contiennent des `$ref` locales (18 occurrences dans
`experiment.schema.json`, 7 dans `fee_schedule.schema.json`) ; le validateur
système les construit et les tests approuvés passent.

Une première exécution du script a produit `58/60` : les deux échecs venaient
du **harnais**, qui avait omis la propriété racine `schema_version.const`
exigée par le registre, provoquant `ContractSchemaMalformedError` avant le
contrôle de référence. Après correction du harnais, `60/60`. Ce n'est pas un
défaut du produit.

**Limite :** `_resolve_pointer` utilise `int(part)` pour les index de tableau.
Il accepte donc `-1`, `+1`, ` 1` et `01`, qui ne sont pas des index JSON
Pointer canoniques. Il accepte aussi une cible située sous une annotation
(`#/default`) si l'objet est structurellement un schéma. La cible reste
validée structurellement ; les contrôles `multipleOf`, mots-clés inconnus et
cycles ne sont pas contournés. C'est un écart de conformité, pas un
contournement P0.

### 3.3 Audit C — erreurs de schéma

| ID | Contrôle | Preuve | Résultat |
|---|---|---|---|
| C-01 | `ContractSchemaUnreadableError` produite directement | test A0 + sondage direct | **PASS** |
| C-02 | Chaîne `ContractApprovalError` → `ContractSchemaUnreadableError` → `OSError` | test A0 + sondage `from_approved` | **PASS** |
| C-03 | `ContractSchemaMismatchError` détectée directement | test A0 + sondage direct | **PASS** |
| C-04 | `ContractSchemaMismatchError` pendant la vérification finale : `ContractApprovalError`, cause conservée, rollback, aucune ligne | test A0 | **PASS** |
| C-05 | Catégorie stable `approval` pour les erreurs normalisées | tests A0 + inspection | **PASS** |
| C-06 | Aucune ligne après erreur de schéma | tests A0 + sondage final unreadable | **PASS** |
| C-07 | Erreur unreadable **pendant la vérification finale** | sondage indépendant | **PASS** |
| C-08 | Permissions Windows réellement refusées | non exécuté | **NON TESTÉ** |

Sondage final indépendant : un schéma valide est chargé, le fichier est ensuite
remplacé par un répertoire après construction du `ContractSpec` mais avant la
vérification finale. Résultat observé :

```text
category approval
cause ContractSchemaUnreadableError
cause2 PermissionError
no_row True
in_transaction False
ok True
```

Cela démontre le chemin final unreadable, la chaîne de causes, le rollback et
l'absence de ligne. `PermissionError` est une sous-classe d'`OSError`; le test
A0 vérifie `OSError` et reste correct.

**Limite :** le test A0 de permission utilise un répertoire au chemin du
fichier, pas un refus de permission Windows réel. Ce point reste non testé.

### 3.4 Audit D — vérification finale et transaction

| ID | Contrôle | Preuve | Résultat |
|---|---|---|---|
| D-01 | Validation initiale avant transaction | inspection `contract_writer.py:518-531` | **PASS** |
| D-02 | `BEGIN IMMEDIATE` avant la vérification finale | inspection `connection.py:218-238` + test A0 | **PASS** |
| D-03 | Relecture du registre/fichier et comparaison du schéma gelé dans la transaction | inspection `contract_writer.py:322-344` | **PASS** |
| D-04 | INSERT après vérification finale, puis relecture de ligne | inspection `contract_writer.py:534-544` | **PASS** |
| D-05 | Échec final → rollback, `in_transaction == False` | test A0 + sondage final unreadable | **PASS** |
| D-06 | Aucune ligne partielle | tests A0 + sondage | **PASS** |
| D-07 | Documentation exacte de l'ordre | `WRITER_INTEGRATION.md:125-166`, `DECISIONS.md` D-055 | **PASS** |
| D-08 | Garantie de concurrence, verrou de fichier ou crash | non testé, non revendiqué | **NON TESTÉ / NON REVENDIQUÉ** |

Le contrôle A0 `test_final_approval_check_runs_inside_transaction` observe
`connection.in_transaction is True`. Le test de mismatch final vérifie la
catégorie, la cause, l'absence de ligne et la transaction fermée. Le sondage
final unreadable confirme le même comportement avec une erreur réelle de
lecture.

La documentation est désormais cohérente avec le code : la vérification
finale est **dans** la transaction, après `BEGIN IMMEDIATE` et avant l'INSERT.
Elle ne verrouille ni le fichier ni le registre. Aucune garantie de concurrence,
de crash après commit ou de reprise n'est revendiquée.

### 3.5 Audit E — non-régression

| ID | Commande / contrôle | Résultat |
|---|---|---|
| E-01 | `pytest tests -q -rxX` | **744 passed** |
| E-02 | `pytest tests --collect-only -q` | **744 tests collected** |
| E-03 | `pytest tests -q --runxfail` | **744 passed** |
| E-04 | `test_p0_candidates.py` | **55 passed** |
| E-05 | contrats négatifs + validité + parité SQL | **261 passed** |
| E-06 | `0007` + validation + writer + validateur système | **110 passed** |
| E-07 | writer + validateur système | **90 passed** |
| E-08 | manifeste de migration | **11 passed** |
| E-09 | politique de connexion | **23 passed** |
| E-10 | sous-ensemble de reproduction | **25 passed, 33 deselected** |
| E-11 | `git diff --check` | **exit 0**, avertissements CRLF uniquement |
| E-12 | `git ls-files schemas/migrations` | **0 fichier suivi** |
| E-13 | Tests supprimés ou affaiblis | aucun constaté ; 717 → 744 (+27), 58 writer, 32 validateur |
| E-14 | Dépendance de production ajoutée | aucune ; `jsonschema` reste dans `tests/requirements-test.txt` |
| E-15 | Intégration A1/A2 | aucune importation du writer hors `storage`/tests |

Les résultats sont cohérents avec le rapport A0 (744/744, 0 xfail, 0 échec
inattendu). Aucun test n'a été supprimé, désactivé ou transformé en `xfail`
pour obtenir ces chiffres. Les 27 tests supplémentaires correspondent aux
ajouts `multipleOf`, `$ref`, erreurs de schéma et vérification finale.

### 3.6 Audit F — traçabilité

| ID | Contrôle | Résultat |
|---|---|---|
| F-01 | Fichiers de la correction finale | `schema_validator.py`, tests writer/validateur, `tests/README.md`, `WRITER_INTEGRATION.md`, `DECISIONS.md`, proposition de gel, rapport A0 |
| F-02 | Migrations `0004`–`0007` | non modifiées par les corrections finales selon les mtimes ; `SHA256SUMS` valide ; **aucun suivi Git** |
| F-03 | Cohérence rapport/code/tests | cohérente sur les points audités ; une imprécision de test mineure (A5-FC-02) |
| F-04 | Commit | aucun ; `git log` reste à 3 commits |
| F-05 | Gel | aucun ; proposition toujours `PROPOSITION`, non prononcée |
| F-06 | Modification non autorisée | aucune modification A5 de production/test/migration ; ce rapport est le seul ajout A5 |

## 4. Commandes et résultats exacts

Depuis `C:\Users\User\polymarket_strategy_lab`, avec
`.\.venv\Scripts\python.exe` :

```text
pytest tests -q -rxX
# 744 passed in 40.66s

pytest tests --collect-only -q
# 744 tests collected in 0.27s

pytest tests -q --runxfail
# 744 passed in 40.05s

pytest tests/integration/test_p0_candidates.py -q
# 55 passed in 9.10s

pytest tests/unit/test_contracts_negative.py \
  tests/unit/test_contracts_schema_validity.py \
  tests/integration/test_contract_sql_parity.py -q
# 261 passed in 5.70s

pytest tests/integration/test_0007_contract_sql_alignment.py \
  tests/unit/test_contract_validation.py \
  tests/integration/test_contract_writer.py \
  tests/unit/test_system_schema_validator.py -q
# 110 passed in 10.11s

pytest tests/integration/test_contract_writer.py \
  tests/unit/test_system_schema_validator.py -q
# 90 passed in 7.43s

pytest tests/integration/test_migration_manifest.py -q
# 11 passed in 0.13s

pytest tests/integration/test_connection_policy.py -q
# 23 passed in 0.38s

pytest tests/integration/test_contract_writer.py -q \
  -k "mutation or registry or forged or row_factory or ignore_check or normal_writer or custom_schema or permissive or from_approved or unreadable or mismatch or final_approval or invalid_approved"
# 25 passed, 33 deselected in 2.19s

git diff --check
# exit 0 ; avertissements CRLF uniquement

git ls-files schemas/migrations
# aucun fichier ; 0 suivi

git log --oneline -3
# 378f993 premier test terminé
# 589996d ajout des plans
# dc5f3e3 premier commit
```

Vérification indépendante des hashes de migration :

```text
0004_consolidation.sql OK
0005_p0_foundations.sql OK
0006_p0_ledger.sql OK
0007_contract_sql_alignment.sql OK
```

Sondages indépendants :

```text
# validateur : multipleOf, refs valides/invalides/cycles
60 passed / 60

# vérification finale unreadable
category approval
cause ContractSchemaUnreadableError
cause2 PermissionError
no_row True
in_transaction False
ok True
```

Première exécution du sondage de références : `58/60`, deux échecs de harnais
(schémas temporaires sans `schema_version.const`, donc rejetés avant le
contrôle de référence). Après correction du harnais : `60/60`. Aucun de ces
échecs n'était un défaut du produit.

Tous les résultats ci-dessus ont été réellement exécutés. Aucun n'est estimé.

## 5. Défauts, limites et écarts reproductibles

### A5-FC-01 — Pointeur JSON local non strict — **Faible**

- **Fichier :** `src/polymarket_lab/validation/schema_validator.py:165-184`
  (`_resolve_pointer`).
- **Scénario reproductible :**
  `SystemSchemaValidator({"$ref": "#/examples/-1", "examples": [...])` ou
  `#/examples/+1`, `#/examples/ 1`, `#/examples/01`. Le pointeur est accepté et
  résolu par indexation Python, alors que ce ne sont pas des index JSON
  Pointer canoniques. `#/default` est également accepté comme cible si
  l'objet est structurellement un schéma.
- **Impact observé :** un schéma dont la référence serait invalide pour un
  parseur JSON Pointer strict peut être accepté. La cible est tout de même
  validée structurellement ; `multipleOf`, les mots-clés inconnus et les
  cycles ne sont pas contournés. Aucun document n'est validé contre une cible
  non validée.
- **Attendu / observé :** attendu, refus d'un pointeur non canonique ;
  observé, acceptation.
- **Test associé :** aucun test A0 sur ce point ; sondage A5 `-1`, `+1`, ` 1`,
  `01` acceptés.
- **Recommandation A0 :** valider strictement les index de tableau
  (`0|[1-9][0-9]*`), refuser les index négatifs, signés, espacés ou à zéro
  initial, et limiter les cibles aux emplacements de sous-schéma. Ajouter des
  tests. **Ne pas appliquer par A5.**
- **Niveau :** faible, conformité ; pas un défaut bloquant P0/P1.

### A5-FC-02 — Paramètre de test non utilisé — **Faible (qualité de test)**

- **Fichier :** `tests/unit/test_system_schema_validator.py:213-221`
  (`test_multiple_of_decimal_audit_cases_are_rejected_before_validation`).
- **Scénario :** le test est paramétré par `document_value` (`0.3`,
  `0.30000000000000004`) mais ne l'utilise pas ; il ne teste que la
  construction du schéma.
- **Impact :** aucun défaut fonctionnel ; le schéma est bien refusé avant
  toute validation de document. En revanche, le nom et le paramètre suggèrent
  une couverture de valeurs de document qui n'existe pas.
- **Test associé :** le test lui-même ; `test_multiple_of_is_rejected_fail_closed`
  couvre déjà les valeurs de `multipleOf`.
- **Recommandation A0 :** supprimer le paramètre inutile ou renommer le test
  pour décrire exactement la construction refusée. **Ne pas appliquer par
  A5.**

### A5-FC-03 — Erreur unreadable finale absente de la suite — **Faible (couverture)**

- **Fichier :** `tests/integration/test_contract_writer.py:813-831` teste
  l'erreur unreadable au chargement initial ; `842-858` teste un mismatch
  final par injection.
- **Scénario :** aucune entrée de la suite ne rend le fichier illisible
  **après** la construction du `ContractSpec` et **avant** la vérification
  finale. Le sondage indépendant A5 l'a fait et a obtenu `ContractApprovalError`
  → `ContractSchemaUnreadableError` → `PermissionError`, sans ligne et avec
  transaction fermée.
- **Impact :** le code est correct sur ce chemin, mais la suite ne le protège
  pas contre une régression.
- **Recommandation A0 :** ajouter un test permanent de ce scénario.
  **Ne pas appliquer par A5.**

### A5-FC-04 — Parcours de test pouvant utiliser `multipleOf`/refs arbitraires — **Limite acceptée / condition**

- **Fichier :** `src/polymarket_lab/storage/contract_writer_testing.py`.
- **Scénario :** un appelant importe `TestContractSpec` et fournit
  `Draft202012Validator` avec un schéma contenant `multipleOf` ou des refs
  récursives ; le parcours de test peut écrire, sans vérification
  d'approbation.
- **Impact :** ce n'est pas le writer normal et le module n'est pas exporté par
  `polymarket_lab.storage`. C'est une limite explicite documentée. Un code
  arbitraire dans le même processus peut toujours importer un module.
- **Attendu / observé :** attendu, parcours de test séparé ; observé, parcours
  de test séparé.
- **Recommandation :** ne jamais importer `contract_writer_testing` dans
  A1/A2 ; maintenir la séparation. Ce n'est pas un défaut du writer normal.

### A5-FC-05 — Migrations non suivies et baseline auto-référentielle — **Info / risque de traçabilité**

- **Fichier :** `schemas/migrations/`, `SHA256SUMS`.
- **Scénario :** les migrations et le manifeste sont non suivis par Git ;
  `SHA256SUMS` atteste l'identité actuelle des fichiers, pas l'authenticité
  historique. Les hashes sont valides ; les mtimes des migrations sont
  antérieurs aux corrections finales.
- **Impact :** impossible de prouver par Git qu'aucune migration n'a été
  modifiée avant ou pendant l'audit. Le test du manifeste passe, mais il est
  auto-référentiel.
- **Recommandation propriétaire :** committer les migrations et le manifeste
  dans une référence auditée, puis faire vérifier cette référence.

### A5-FC-06 — TOCTOU / concurrence / crash — **Info / non testé**

- **Fichier :** `WRITER_INTEGRATION.md:156-166`, `contract_writer.py:322-344`.
- **Scénario :** le fichier ou le registre peut changer entre la vérification
  finale et l'INSERT ; aucun verrou de fichier ; aucun test de concurrence,
  de crash après commit ou de reprise.
- **Impact :** non revendiqué comme garanti par A0 ; la vérification finale
  réduit la fenêtre mais ne l'élimine pas.
- **Recommandation :** conserver la limite documentée ; ne pas présenter ce
  contrôle comme une garantie de concurrence.

### A5-FC-07 — Choix A/B du validateur de production non tranché — **Décision propriétaire**

- **Fichier :** `WRITER_INTEGRATION.md:281-321`, `DECISIONS.md`.
- **Scénario :** `jsonschema` reste une dépendance de test ; le writer normal
  utilise `SystemSchemaValidator`, un sous-ensemble interne fail-closed.
- **Impact :** l'intégration A1/A2 en production reste bloquée ; le writer est
  un candidat Option B non approuvé.
- **Recommandation :** décision explicite du propriétaire avant toute
  production ; aucune décision ne peut être prise par A5.

### A5-FC-08 — Helper générique avec validateur fourni — **Info / limite de périmètre**

- **Fichier :** `src/polymarket_lab/validation/contracts.py:228-243`.
- **Scénario :** `validate_contract` accepte un validateur fourni par
  l'appelant et peut donc valider un document contre un schéma contenant
  `multipleOf`.
- **Impact :** ce helper ne réalise aucune écriture et n'est pas le chemin
  d'approbation du writer normal. C'est une API générique, pas un contournement
  du writer.
- **Recommandation :** ne pas l'utiliser comme preuve d'approbation ; le
  writer normal reste la référence.

### A5-FC-09 — Code arbitraire dans le processus — **Limite assumée**

- **Impact :** les attributs privés, globals, fonctions et objets gelés peuvent
  être remplacés par du code Python arbitraire. Aucune isolation de processus.
- **Recommandation :** ne pas présenter le gel comme une frontière de sécurité ;
  le document A0 le reconnaît déjà.

### A5-FC-10 — Aucun writer A1/A2 réel — **Info / non testé**

- **Impact :** aucune preuve d'intégration réelle, de latence, de concurrence
  applicative ou de comportement A1/A2.
- **Recommandation :** intégration expérimentale locale séparée et auditée
  avant toute utilisation.

## 6. Risques résiduels

1. **Sous-ensemble JSON Schema :** `multipleOf` et les schémas récursifs sont
   refusés ; des mots-clés non supportés le sont aussi. Ce n'est pas une
   conformité complète ; un futur contrat peut être refusé comme inutilisable.
2. **Validateur de production non approuvé :** Option A/B non tranchée ;
   `jsonschema` reste test-only.
3. **TOCTOU :** la vérification finale relit le fichier dans la transaction,
   mais un changement entre cette lecture et l'INSERT reste possible ; aucun
   verrou de fichier.
4. **Concurrence/crash/reprise :** aucun test ; aucune garantie.
5. **Permission réelle :** seule une `OSError` par répertoire a été testée ;
   un refus de permission Windows réel n'est pas prouvé.
6. **Migrations :** non suivies par Git ; baseline auto-référentielle.
7. **Parcours de test :** `contract_writer_testing` peut utiliser des schémas
   et validateurs arbitraires ; ne pas l'importer en A1/A2.
8. **Pointeur JSON non strict :** index non canoniques et cibles sous
   annotation acceptés ; pas de contournement des contrôles P0/P1, mais écart
   de conformité.
9. **Restrictions de connexion :** type exact `sqlite3.Connection` et
   `row_factory` limité ; des wrappers légitimes sont refusés.
10. **Code arbitraire :** pas d'isolation de processus ; le gel n'est pas une
    frontière de sécurité.
11. **Périmètre :** seuls `experiment` et `fee_schedule` sont couverts.
12. **INSERT direct :** contourne le writer ; non couvert.

## 7. Décisions encore nécessaires

1. **Option A ou B** pour la validation de production : `jsonschema` épinglé
   en dépendance de production, ou adoption/maintenance du validateur interne.
2. **Politique `multipleOf`** pour les futurs contrats : refus définitif,
   sémantique décimale explicite, ou passage à un validateur de référence.
3. **Référence Git auditée** pour les migrations et `SHA256SUMS`.
4. **Politique de connexion** : maintenir le type exact/`row_factory` limité,
   ou définir une interface de wrapper supportée.
5. **Autorisation d'une intégration expérimentale locale A1/A2**, séparée de
   toute production et de tout gel.
6. **Décision de gel** : aucune ; le propriétaire doit la prononcer
   explicitement après un audit de sortie de candidat.

## 8. Recommandation finale

Les corrections finales A5-C2-01 à A5-C2-04 sont **acceptées comme closes dans
le périmètre audité**. Le writer reste **candidat non approuvé**, avec un
verdict global **PARTIAL**.

Conditions minimales si le propriétaire autorise une utilisation expérimentale
locale :

- n'utiliser que les contrats approuvés `experiment` et `fee_schedule` ;
- ne pas introduire `multipleOf` ni de schéma récursif sans nouvelle décision ;
- ne pas importer `contract_writer_testing` dans A1/A2 ;
- ne pas supposer de garantie de concurrence, de crash ou de reprise ;
- ne pas utiliser de base réelle ni de clé réelle ;
- ne pas prononcer de gel ni d'approbation de production.

Avant toute production, il reste nécessaire de trancher l'option A/B, de
renforcer la conformité du validateur et du pointeur JSON, de tester les
permissions réelles, la concurrence, le crash et la reprise, le packaging hors
dépôt et l'intégration A1/A2, puis de committer une référence Git des migrations
et du manifeste.

## 9. Fichiers modifiés, non suivis et état des migrations

### 9.1 Correction finale A0 auditée

Selon `tests/REPORT_A0_FINAL_CANDIDATE_FIXES.md` et l'inspection :

- `src/polymarket_lab/validation/schema_validator.py` ;
- `tests/unit/test_system_schema_validator.py` ;
- `tests/integration/test_contract_writer.py` ;
- `tests/README.md` ;
- `WRITER_INTEGRATION.md` ;
- `DECISIONS.md` (D-055) ;
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` (statistique datée) ;
- `tests/REPORT_A0_FINAL_CANDIDATE_FIXES.md` (rapport).

Aucun fichier de migration, de dépendance de production, de code A1/A2 ou de
test A5 antérieur n'a été modifié par les corrections finales selon le rapport
A0 et les mtimes observés.

### 9.2 Ajout A5

Ce rapport : `tests/REPORT_A5_FINAL_CANDIDATE_AUDIT.md` — **non suivi**, ajouté
par A5. A5 n'a modifié aucun fichier de production, aucun test, aucune
migration et n'a effectué aucun commit.

### 9.3 État Git observé avant cet ajout

`git status --short` comptait 80 entrées, dont les fichiers de travail
antérieurs non commités. Liste observée :

```text
 M ARCHITECTURE.md
 M COORDINATION.md
 M DECISIONS.md
 M README.md
 M agents/AGENT_A1_DATA.md
 M agents/AGENT_A2_SIMULATION.md
 M configs/app.example.yaml
 M contracts/CONTRACT_FREEZE_PROPOSAL.md
 M contracts/README.md
 M contracts/examples/execution_assumptions.json
 M contracts/examples/execution_estimate.json
 M contracts/examples/execution_result.json
 M contracts/examples/experiment.json
 M contracts/examples/fee_schedule.json
 M contracts/examples/market_event_book_delta.json
 M contracts/examples/market_event_book_snapshot.json
 M contracts/examples/market_event_connection_status.json
 M contracts/examples/market_event_market_metadata.json
 M contracts/examples/market_event_market_resolution.json
 M contracts/examples/market_event_trade.json
 M contracts/examples/market_event_trader_activity.json
 M contracts/examples/order_intent.json
 M contracts/execution.schema.json
 M contracts/experiment.schema.json
 M contracts/fee_schedule.schema.json
 M contracts/market_event.schema.json
 M schemas/initial_db_schema.sql
 M src/polymarket_lab/storage/__init__.py
 M src/polymarket_lab/validation/__init__.py
?? WRITER_INTEGRATION.md
?? contracts/examples/execution_result_missing_book.json
?? schemas/migrations/
?? src/polymarket_lab/storage/clock.py
?? src/polymarket_lab/storage/connection.py
?? src/polymarket_lab/storage/contract_writer.py
?? src/polymarket_lab/storage/contract_writer_testing.py
?? src/polymarket_lab/storage/replacements.py
?? src/polymarket_lab/validation/contracts.py
?? src/polymarket_lab/validation/immutability.py
?? src/polymarket_lab/validation/registry.py
?? src/polymarket_lab/validation/schema_validator.py
?? tests/README.md
?? tests/REPORT_A0_A5_06_FIX.md
?? tests/REPORT_A0_CONTRACT_SQL_ALIGNMENT.md
?? tests/REPORT_A0_FINAL_CANDIDATE_FIXES.md
?? tests/REPORT_A0_P0_REAUDIT_FIXES.md
?? tests/REPORT_A0_SQL_CORRECTIONS.md
?? tests/REPORT_A0_WRITER_HARDENING.md
?? tests/REPORT_A0_WRITER_HARDENING_2.md
?? tests/REPORT_A0_WRITER_VALIDATION_INTEGRATION.md
?? tests/REPORT_A5_A5_06_FINAL_AUDIT.md
?? tests/REPORT_A5_AUDIT_POST_0007.md
?? tests/REPORT_A5_CONTRACTS.md
?? tests/REPORT_A5_CONTRACT_WRITER_AUDIT.md
?? tests/REPORT_A5_P0_AUDIT.md
?? tests/REPORT_A5_P0_FINAL_REAUDIT.md
?? tests/REPORT_A5_P0_REAUDIT.md
?? tests/REPORT_A5_POST_HARDENING_2_AUDIT.md
?? tests/REPORT_A5_POST_HARDENING_AUDIT.md
?? tests/accounting/test_ledger_invariants.py
?? tests/conftest.py
?? tests/integration/test_0007_contract_sql_alignment.py
?? tests/integration/test_connection_policy.py
?? tests/integration/test_consolidation_0004.py
?? tests/integration/test_contract_sql_parity.py
?? tests/integration/test_contract_writer.py
?? tests/integration/test_idempotence.py
?? tests/integration/test_migration_manifest.py
?? tests/integration/test_p0_candidates.py
?? tests/integration/test_schema_sqlite.py
?? tests/labtest/
?? tests/requirements-test.txt
?? tests/unit/test_contract_semantics.py
?? tests/unit/test_contract_validation.py
?? tests/unit/test_contracts_examples.py
?? tests/unit/test_contracts_negative.py
?? tests/unit/test_contracts_schema_validity.py
?? tests/unit/test_core_spec_vectors.py
?? tests/unit/test_execution_assumptions_parity.py
?? tests/unit/test_system_schema_validator.py
```

### 9.4 Migrations

Fichiers présents :

```text
schemas/migrations/0004_consolidation.sql
schemas/migrations/0005_p0_foundations.sql
schemas/migrations/0006_p0_ledger.sql
schemas/migrations/0007_contract_sql_alignment.sql
schemas/migrations/run_migration.py
schemas/migrations/SHA256SUMS
schemas/migrations/README.md
```

- `git ls-files schemas/migrations` : **0** fichier suivi.
- `SHA256SUMS` : les quatre hashes ont été recalculés et sont corrects.
- Mtimes : les fichiers `0004`–`0007` sont à 08:03–16:18, `SHA256SUMS` à
  18:11 et son README à 18:14 ; les corrections finales
  (`schema_validator.py`, tests, documentation) sont à 19:24–19:33. Tout le
  jeu de migrations est donc antérieur aux corrections finales.
- Le manifeste est **auto-référentiel** : il prouve l'identité courante, pas
  l'historique Git.

## 10. Conclusion

- **P0-A `multipleOf` : PASS** dans le périmètre du writer normal et du
  validateur système.
- **P0-B `$ref` : PASS** pour les cibles, les externalités et les cycles ; un
  écart faible de pointeur JSON subsiste, sans contournement des contrôles
  P0/P1.
- **P1-A erreurs de schéma : PASS** pour les chemins testés, y compris le
  sondage indépendant unreadable final ; la permission réelle et un test
  permanent de ce chemin restent à ajouter.
- **P1-B vérification finale : PASS** sur l'ordre, le rollback et l'absence de
  ligne ; aucune garantie de concurrence/crash n'est revendiquée et aucune ne
  doit l'être.
- **Non-régression : PASS** (744/744, 0 xfail, 0 skip, cibles cohérentes).
- **Traçabilité : PARTIAL** (migrations non suivies, baseline auto-référentielle,
  arbre de travail non commité).

**Verdict final : PARTIAL.** Les corrections finales sont acceptées ; le
writer reste un candidat, sans gel ni approbation de production.
