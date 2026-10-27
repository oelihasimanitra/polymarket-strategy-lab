# Rapport A0 — corrections après ré-audit A5 P0

> **Mise à jour A5-06 (2026-10-27).** Les chiffres `600/598/2` de ce rapport
> décrivent l'état **avant** la correction A5-06 et sont conservés comme
> mesure historique. L'état courant est **717 collectés, 717 réussis,
> 0 xfail**. Voir `tests/REPORT_A0_CONTRACT_SQL_ALIGNMENT.md` et
> `tests/REPORT_A0_WRITER_VALIDATION_INTEGRATION.md`.

**Date :** 2026-10-27  
**Auteur :** A0 — architecte / intégrateur  
**Objet :** corriger les anomalies A5-REAUDIT-01 à -04 et intégrer les
vérifications manquantes dans la suite automatisée.  
**Statut :** corrections appliquées ; **aucun commit**, **aucun gel**, aucune
migration sur une base réelle. Les migrations restent des candidats non
approuvés.

## 1. Fichiers modifiés

- `schemas/migrations/0006_p0_ledger.sql`
- `schemas/migrations/README.md`
- `ARCHITECTURE.md` — invariants de provenance des conversions
- `DECISIONS.md` — D-045 précisée
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` — statistiques historisées/actualisées
- `tests/README.md` — chiffres courants, contrôles manuels vs automatisés
- `tests/integration/test_p0_candidates.py` — nouveaux tests
- `tests/REPORT_A0_SQL_CORRECTIONS.md` — bannière historique
- `tests/REPORT_A5_P0_AUDIT.md` — bannière historique
- `tests/REPORT_A5_P0_REAUDIT.md` — bannière historique
- `tests/REPORT_A0_P0_REAUDIT_FIXES.md` — présent rapport

## 2. Anomalies corrigées

### A5-REAUDIT-01 — provenance des conversions

**Règle appliquée :** une conversion n'est rattachée qu'à une transaction du
ledger de la même expérience avec :

```text
ref_type = 'market_resolution'
ref_id   = resolution_event_id
kind     = 'settlement'
```

Modifications dans `0006_p0_ledger.sql` :

- préflight `_preflight_conversion_experiment` : filtre `kind='settlement'` ;
- dérivation de `experiment_id` : filtre `kind='settlement'` ;
- trigger `trg_settlement_conversions_provenance` : filtre `kind='settlement'`.

Conséquences testées :

| Cas | Résultat |
|---|---|
| settlement correspondant | accepté |
| adjustment seul | rejeté |
| aucune transaction de ledger | rejeté |
| settlement dans une seule expérience | conversion rattachée à cette expérience |
| même résolution dans deux expériences, settlement dans une seule | accepté, rattaché au settlement |
| plusieurs settlements candidats | rejeté (branche défensive, voir limites) |

Aucun rejet ne supprime de ligne : les tests vérifient `user_version`, le
journal et les comptages après échec. L'ancien test d'ambiguïté fondé sur un
`adjustment` a été remplacé par
`test_0006_settlement_in_one_experiment_ignores_adjustment_in_other` : son
hypothèse initiale était précisément l'anomalie A5-REAUDIT-01. Aucune couverture
n'est supprimée ; le cas « plusieurs settlements » est couvert séparément.

### A5-REAUDIT-02 — tests de portée et de normalisation

Ajouts dans `tests/integration/test_p0_candidates.py` :

- `test_replacement_scope_rejects_different_source`
- `test_replacement_scope_rejects_different_event_type`
- `test_replacement_scope_rejects_different_market_or_token`
- `test_replacement_scope_rejects_different_token_same_market`
- `test_replacement_normalizer_must_match_new_event`
- `test_replacement_scope_accepts_same_source_type_market_token`

Les quatre rejets et l'acceptation positive sont désormais protégés par la
suite committée.

### A5-REAUDIT-03 — runner 5→6 et comptages

Ajouts :

- `test_runner_5_to_6_success_journal_backup_and_counts` : parcours réel du
  runner, `user_version=6`, journal `[4,5,6]`, sauvegarde v5, intégrité, FK,
  comptages.
- `test_runner_5_to_6_preflight_failure_restores_v5` : échec préflight,
  restauration v5, journal `[4,5]`, données intactes, sauvegarde présente.
- `test_runner_5_to_6_post_commit_failure_restores_v5` : échec post-commit
  simulé, restauration v5, données intactes, sauvegarde présente.

Les comptages couvrent désormais :

- `market_events`, `event_replacements`, `data_manifests`, `experiments`,
  `ledger_transactions`, `ledger_postings`, `settlement_conversions`,
  `simulated_orders`, `simulated_fills` ;
- les tests 0005 vérifient aussi `fee_schedules`, `hypotheses`, `strategies`.

### A5-REAUDIT-04 — statistiques et rapports

- `tests/README.md` : chiffres de cette campagne (avant A5-06) **600
  collectés, 598 réussis, 2 xfail** et P0 **55 réussis**.
- `contracts/CONTRACT_FREEZE_PROPOSAL.md` : la ligne 472/470/2 est marquée
  **historique** ; une ligne 600/598/2 est ajoutée.
- `tests/REPORT_A0_SQL_CORRECTIONS.md` : bannière **RAPPORT HISTORIQUE**.
- `tests/REPORT_A5_P0_AUDIT.md` et `tests/REPORT_A5_P0_REAUDIT.md` : bannières
  **RAPPORT HISTORIQUE** ; leurs chiffres ne sont pas l'état courant.
- Les contrôles manuels 19/19, 13/13 et 4/4 sont documentés dans
  `tests/README.md` avec date, méthode et distinction vis-à-vis des tests
  automatisés.

## 3. Résultats des commandes réellement exécutées

### Suite complète

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q -rxX
```

**À cette date : 600 collectés, 598 réussis, 2 xfail, 0 échec inattendu.**

Les 2 xfail sont A5-06 :

- `test_fee_schedule_effective_period_must_be_ordered`
- `test_experiment_period_must_be_chronological`

### Tests P0 ciblés

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_p0_candidates.py -q
```

**55 réussis.**

### `--runxfail`

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --runxfail
```

**598 réussis, 2 échoués** — uniquement les deux anomalies A5-06 attendues.

### Contrôles manuels sur base synthétique

Base isolée :
`%TEMP%\polymarket_p0_dry_run_20261027_1430` (aucune donnée réelle).

| Sonde | Périmètre | Résultat |
|---|---|---:|
| `probe_c01_c02_c03.py` | C-01/C-02/C-03 sur base synthétique migrée (v6 en dernier) | 19/19 PASS |
| `probe_0006.py` | contraintes 0006, ledger, conversions, `REPLACE` | 13/13 PASS |
| `probe_recovery.py` | échec avant/après COMMIT, FK/RT, sauvegardes | 4/4 PASS |

Ces scripts ne sont pas committés. Les cas correspondants sont couverts par les
tests automatisés lorsque possible.

### Propreté

```powershell
git diff --check
```

Aucune erreur ; seuls les avertissements CRLF globaux de Git subsistent.

## 4. Comptages du dry-run synthétique

Source `0.4` → `0.5` → `0.6` :

| Table | Avant 0005 | Après 0005 | Après 0006 |
|---|---:|---:|---:|
| `market_events` | 8 | 8 | 8 |
| `event_replacements` | 1 | 1 | 1 |
| `data_manifests` | 1 | 1 | 1 |
| `experiments` | 2 | 2 | 2 |
| `ledger_transactions` | 2 | 2 | 2 |
| `ledger_postings` | 5 | 5 | 5 |
| `settlement_conversions` | 1 | 1 | 1 |
| `simulated_orders` | 1 | 1 | 1 |
| `simulated_fills` | 2 | 2 | 2 |

La conversion `conv_one` est rattachée à `exp_fixture_001` après 0006.

Cas complémentaires sur copies :

- conversion sans settlement : 0006 refusée, `user_version` reste 5, données
  intactes ;
- même résolution avec settlement dans `exp_fixture_001` et adjustment dans
  `exp_fixture_002` : 0006 acceptée, les deux conversions sont rattachées à
  `exp_fixture_001` ;
- plusieurs settlements candidats : refus défensif sans perte.

## 5. Limites restantes

1. **Aucune base de travail réelle** n'existe dans le dépôt ; les preuves sont
   synthétiques. Aucune migration réelle n'a été exécutée.
2. **Plusieurs settlements candidats** ne peuvent pas exister dans un 0.5
   valide à cause de l'unicité globale `(ref_type, ref_id, kind)`. Le test
   correspondant utilise une copie 0.5 **volontairement corrompue** pour
   exercer la branche défensive ; ce n'est pas un schéma source valide.
3. Le message du préflight 0006 reste générique
   (`CHECK constraint failed: bad = 0`), même si le rejet est effectif.
4. C-02 : SQL ne prouve pas l'horloge murale pour un accès direct ; seule l'API
   de stockage garantit l'horodatage.
5. C-03 : un `SELECT` privilégié direct peut lire les tables brutes ; les vues
   as-of exigent le seal.
6. Les contrats `1.2.0` et les migrations `0.5`/`0.6` restent des candidats non
   approuvés, non gelés.

## 6. Confirmation

- Aucune base de travail réelle n'a été ouverte en écriture ni modifiée.
- Aucune collecte Polymarket, aucune simulation de trading, aucune installation
  réseau.
- Aucun commit.
- Aucun gel des contrats.
- Aucun test existant supprimé ou désactivé.
- Les contrats audités `1.1.0` et le schéma SQL `0.4` n'ont pas été modifiés.
