# Rapport A0 — corrections finales du candidat writer

**Date :** 2026-10-27  
**Auteur :** A0 — architecte / intégrateur  
**Objet :** traiter les réserves de
`tests/REPORT_A5_POST_HARDENING_2_AUDIT.md` avant un nouvel audit A5.  
**Statut :** writer **candidat non approuvé**. Aucun commit, aucun gel, aucune
collecte, aucune simulation, aucune base réelle, aucune dépendance de
production ajoutée, aucune migration `0005`/`0006`/`0007` modifiée.

---

## 1. Résumé exécutif

Les deux anomalies fonctionnelles du validateur système sont fermées :

- `multipleOf` est **refusé à la construction** (option B de la mission) :
  sa sémantique décimale divergeait de `jsonschema` et aucun contrat approuvé
  ne l'utilise ;
- les `$ref` sont vérifiées à la construction : cible existante, cible de type
  schéma objet, absence de cycle. Les références distantes, les cibles
  non-schéma et les cycles sont refusés.

Les erreurs `ContractSchemaUnreadableError` et `ContractSchemaMismatchError`
sont désormais testées directement et via le writer, avec conservation des
causes et absence de ligne.

La vérification finale d'approbation reste **dans la transaction**, après
`BEGIN IMMEDIATE` et avant l'INSERT. Ce comportement est correct : il réduit la
fenêtre TOCTOU et garantit le rollback en cas d'échec. La documentation a été
corrigée pour décrire exactement cet ordre ; le contrôle n'a pas été déplacé
artificiellement.

Résultats : **744 tests collectés, 744 réussis, 0 xfail, 0 échec inattendu**
(contre 717 dans l'audit précédent).

---

## 2. Fichiers modifiés ou ajoutés

### Code

- `src/polymarket_lab/validation/schema_validator.py` —
  `multipleOf` refusé explicitement ; `$ref` vérifiées à la construction
  (cible objet valide, cycles refusés) ; suppression du calcul `multipleOf`.

### Tests

- `tests/unit/test_system_schema_validator.py` — 32 tests (contre 12).
  Ajout de `multipleOf`, des références valides/invalides/cycliques et des
  contrôles de construction.
- `tests/integration/test_contract_writer.py` — 58 tests (contre 51).
  Ajout de `ContractSchemaUnreadableError`, `ContractSchemaMismatchError`,
  de la vérification finale dans la transaction, et des schémas approuvés
  invalides sans écriture.
- `tests/README.md` — chiffres, couverture, limites.

### Documentation et décisions

- `WRITER_INTEGRATION.md` — ordre exact avant/dans la transaction, portée de
  la vérification finale, `multipleOf` et `$ref`.
- `DECISIONS.md` — nouvelle D-055.
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` — statistique datée 744.
- `tests/REPORT_A0_FINAL_CANDIDATE_FIXES.md` — présent rapport.

**Non modifiés :** migrations `0004` à `0007`, rapports A5, index/historique
Git, fichiers de dépendances de production.

---

## 3. Anomalies traitées

### 3.1 A5-C2-01 — `multipleOf` décimal

**Décision : option B — refus explicite.**

`multipleOf` est retiré du sous-ensemble supporté. `SystemSchemaValidator`
lève `UnsupportedSchemaError` à la construction, avec un message explicite.
Aucun document n'est évalué avec ce mot-clé.

Tests ajoutés :

- valeurs `0.1`, `0.3`, `0.30000000000000004`, `1`, `2`, `-1`, `0`,
  `1e-12`, `1e308` : toutes refusées à la construction ;
- cas A5 `multipleOf: 0.1` avec les valeurs de document `0.3` et
  `0.30000000000000004` : le schéma est refusé avant toute validation ;
- vérification qu'aucun schéma approuvé `experiment`/`fee_schedule` ne
  contient `multipleOf` ;
- schéma approuvé invalide contenant `multipleOf` : le writer lève
  `ContractApprovalError` avec cause `UnsupportedSchemaError` et n'écrit
  aucune ligne.

**Classification : CORRIGÉE ET TESTÉE.**

Conséquence : un futur contrat qui utilise `multipleOf` sera refusé comme
inutilisable jusqu'à une décision explicite (implémentation décimale correcte
ou adoption d'un validateur de référence).

### 3.2 A5-C2-02 — `$ref` cible non-schéma / cycles

Le sous-ensemble `$ref` est précisément :

- références locales `#/...` uniquement ;
- la cible doit exister et être un schéma objet ;
- la cible est validée structurellement à la construction ;
- les cycles de références sont refusés à la construction ;
- le contrôle de profondeur à l'exécution reste une défense secondaire.

Tests ajoutés :

- référence valide vers `$defs` : construction et validation correctes ;
- cible inexistante : refus à la construction ;
- cible non-schéma (`#/examples/0`) : refus à la construction ;
- cycle direct et cycle mutuel : refus à la construction ;
- référence distante : refus ;
- cible objet contenant un mot-clé non supporté : refus ;
- schéma approuvé invalide (cible non-schéma, cycle) : `ContractApprovalError`
  avec cause `UnsupportedSchemaError`, aucune ligne écrite.

**Classification : CORRIGÉE ET TESTÉE.**

Limite : les schémas récursifs valides en JSON Schema sont refusés. C'est un
choix fail-closed documenté, pas une conformité complète.

### 3.3 A5-C2-03 — ordre documenté approbation/transaction

Le comportement a été inspecté avant toute modification :

- **avant la transaction** : contrôle de connexion, chargement du registre et
  du fichier, hash/version, gel, construction du validateur système,
  validation schéma → chronologie → version → métier, mapping des valeurs ;
- **dans la transaction** : `BEGIN IMMEDIATE`, relecture du registre et du
  fichier, comparaison du schéma gelé, vérification du validateur système,
  puis INSERT et relecture de la ligne.

Le contrôle final est conservé dans la transaction car il réduit la fenêtre
entre la dernière lecture du schéma et l'INSERT. Il ne verrouille pas le
fichier ni le registre. `BEGIN IMMEDIATE` empêche un autre écrivain SQLite
concurrent, pas une modification de fichier.

Tests ajoutés :

- la vérification finale est observée avec `connection.in_transaction is True` ;
- une erreur `ContractSchemaMismatchError` pendant cette vérification produit
  `ContractApprovalError`, rollback et aucune ligne.

La documentation de `WRITER_INTEGRATION.md` décrit désormais exactement cet
ordre et ses limites.

**Classification : CORRIGÉE ET TESTÉE** (documentation et absence d'écriture).
Aucune garantie de concurrence ou de TOCTOU n'est revendiquée.

### 3.4 A5-C2-04 — erreurs de schéma non testées

- `ContractSchemaUnreadableError` : un répertoire placé au chemin du fichier de
  schéma force une `OSError` réelle sur `Path.read_bytes()` ; le writer lève
  `ContractApprovalError` avec cause `ContractSchemaUnreadableError`, dont la
  cause est l'`OSError` d'origine. Aucune ligne.
- `ContractSchemaMismatchError` : test direct de `verify_approved_schema` avec
  un schéma modifié ; test writer par injection de l'erreur dans la
  vérification finale, avec rollback et aucune ligne.

**Classification : CORRIGÉE ET TESTÉE.**

Limite : le test simule une `OSError` par un répertoire ; il ne teste pas un
refus de permission Windows réel.

### 3.5 Points laissés ouverts

- **A5-C2-05** : baseline de manifeste toujours auto-référentielle ; les
  migrations restent non suivies par Git. **NON VÉRIFIABLE** sans commit de
  référence.
- **A5-C2-06** : aucun writer A1/A2 réel. **NON VÉRIFIABLE**.
- **A5-C2-07** : validateur système non approuvé pour la production ; décision
  A/B propriétaire en attente. **NON CORRIGÉE** par conception.
- **A5-C2-08** : code arbitraire dans le processus. Limite assumée, non
  revendiquée comme sécurité.
- **A5-C2-09** : concurrence, crash, reprise non testés. **NON VÉRIFIABLE**.
- Permission réelle, packaging hors dépôt, suite de conformité JSON Schema
  externe : non exécutés.

---

## 4. Tests réellement exécutés et résultats

Depuis `C:\Users\User\polymarket_strategy_lab`, avec
`.\.venv\Scripts\python.exe` :

```text
pytest tests -q -rxX
# 744 passed in 34.68s

pytest tests --collect-only -q
# 744 tests collected in 0.17s

pytest tests -q --runxfail
# 744 passed in 28.57s

pytest tests/integration/test_p0_candidates.py -q
# 55 passed in 6.17s

pytest tests/unit/test_contracts_negative.py \
  tests/unit/test_contracts_schema_validity.py \
  tests/integration/test_contract_sql_parity.py -q
# 261 passed in 3.21s

pytest tests/integration/test_0007_contract_sql_alignment.py \
  tests/unit/test_contract_validation.py \
  tests/integration/test_contract_writer.py \
  tests/unit/test_system_schema_validator.py -q
# 110 passed in 9.31s

pytest tests/integration/test_contract_writer.py \
  tests/unit/test_system_schema_validator.py -q
# 90 passed in 6.07s

pytest tests/integration/test_migration_manifest.py -q
# 11 passed in 0.22s

pytest tests/integration/test_connection_policy.py -q
# 23 passed in 0.45s

pytest tests/integration/test_contract_writer.py -q \
  -k "mutation or registry or forged or row_factory or ignore_check or normal_writer or custom_schema or permissive or from_approved or unreadable or mismatch or final_approval or invalid_approved"
# 25 passed, 33 deselected in 2.17s

git diff --check
# exit 0 ; avertissements CRLF uniquement

git ls-files schemas/migrations
# aucun fichier ; 0 suivi
```

Aucun de ces résultats n'est estimé. La suite complète a été exécutée après
les modifications de code et de tests.

---

## 5. Risques résiduels

1. **Sous-ensemble JSON Schema.** `multipleOf` est refusé ; les schémas
   récursifs sont refusés ; la conformité complète n'est pas prouvée.
2. **TOCTOU.** La vérification finale relit le fichier dans la transaction,
   mais un changement entre cette lecture et l'INSERT reste possible.
3. **Concurrence/crash/reprise.** Aucun test ; aucune garantie.
4. **Code arbitraire dans le processus.** Les attributs privés, globals et
   fonctions peuvent être remplacés. Aucune isolation de processus.
5. **Manifeste/Git.** Baseline auto-référentielle ; historique non prouvé.
6. **Dépendance de validation.** Option A/B non tranchée ; intégration A1/A2
   bloquée.
7. **Périmètre.** Seuls `experiment` et `fee_schedule` sont couverts.
8. **INSERT direct.** Contourne le writer.
9. **Restrictions de connexion.** Les wrappers et sous-classes légitimes de
   `sqlite3.Connection` sont refusés.
10. **Permission réelle.** Seule une `OSError` par répertoire a été testée.

---

## 6. Contrôles non réalisés

- Concurrence multi-connexions, verrou, timeout, crash après commit, reprise.
- Permission de fichier réelle sur un système configuré pour refuser la
  lecture.
- Packaging installé hors du dépôt.
- Suite de conformité JSON Schema externe complète.
- Writer A1/A2 réel, collecte Polymarket, simulation, base réelle.
- Preuve d'historique Git des migrations.
- Gel des contrats.

---

## 7. Décisions encore nécessaires

1. **Option A ou B de validation de production** :
   - A : `jsonschema` épinglé en dépendance de production ;
   - B : adopter `SystemSchemaValidator`, en acceptant le sous-ensemble et en
     maintenant sa suite de conformité.
   Sans décision, l'intégration A1/A2 reste bloquée.
2. **Souhait éventuel de supporter `multipleOf`** : cela exige une sémantique
   décimale explicite et des tests de limites, ou le passage à `jsonschema`.
3. **Commit Git de référence** pour les migrations et `SHA256SUMS`.
4. **Restrictions de connexion** : maintenir le type exact et
   `row_factory` limité, ou définir une interface de wrapper supportée.
5. **Autorisation d'un nouvel audit A5** puis, séparément, d'une intégration
   expérimentale locale.

---

## 8. Recommandation pour le prochain audit A5

Vérifier indépendamment :

1. le refus de `multipleOf` à la construction, y compris les cas décimaux
   A5-C2-01 et les valeurs négatives/nulles ;
2. les `$ref` valides, cibles absentes, cibles non-schéma, cycles, références
   distantes et absence d'écriture ;
3. `ContractSchemaUnreadableError` et `ContractSchemaMismatchError`, chaînes de
   causes et catégories ;
4. la position réelle de la vérification finale (dans `BEGIN IMMEDIATE`, avant
   l'INSERT) et le rollback sans ligne ;
5. l'absence de régression sur les 717 tests précédents et les 27 nouveaux ;
6. l'absence de modification des migrations, des rapports A5 et des
   dépendances de production.

Le writer reste un **candidat**. Aucun gel, aucun commit, aucune autorisation
de production n'est prononcé par ce rapport.
