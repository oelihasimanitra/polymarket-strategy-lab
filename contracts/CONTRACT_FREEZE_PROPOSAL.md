# Proposition de gel des contrats et critères d'acceptation

**Date :** 2026-10-26, mise à jour 2026-10-27
**Auteur :** A0 — architecte / intégrateur
**Statut :** PROPOSITION — gel non prononcé. Références auditées : contrats
`1.1.0`, SQL `0.4`. Candidats P0 préparés : contrats `1.2.0`, SQL `0.5`/`0.6`/`0.7`.
**Objets proposés au gel (après validation des candidats) :**
- contrats JSON `1.2.0` : `market_event`, `execution`, `experiment` et
  `fee_schedule` ; `strategy_hypothesis` reste `1.0.0` ;
- schéma SQL base `0.3` + `0004_consolidation.sql` (0.4) +
  `0005_p0_foundations.sql` (0.5) + `0006_p0_ledger.sql` (0.6) +
  `0007_contract_sql_alignment.sql` (0.7) ;
- conventions de `ARCHITECTURE.md` version `0.5` (candidat) ;
- décisions D-009 à D-024, D-027 à D-053 (D-028, D-031, D-033, D-037, D-039
  sous réserve ; D-042 à D-053 au statut PRÉPARÉ, non approuvées).

Aucun test réseau n'a été exécuté par A0. Les conclusions Polymarket intégrées
proviennent de la vérification documentaire rapportée par le propriétaire le
2026-10-26 ; elles ne constituent pas un test d'endpoint.

## 1. Conditions préalables au gel

1. Le propriétaire approuve les critères d'acceptation de ce document.
2. A5 committe les tests de contrat et de schéma listés en §6, et ils passent
   sur une base SQLite neuve.
3. Les points bloquants de §7 sont soit résolus, soit explicitement différés
   avec une étiquette « non définitif » dans les rapports.
4. A1 et A2 acceptent par écrit les interfaces de `ARCHITECTURE.md` §6.
5. Le propriétaire met à jour `COORDINATION.md` et `agents/AGENT_A1_DATA.md`
   pour inclure `src/polymarket_lab/core/` dans le périmètre d'A1 (D-017).

Tant que ces conditions ne sont pas remplies, les agents peuvent travailler sur
fixtures, mais aucune interface n'est déclarée gelée.

## 2. Ce que le gel couvre

- Noms, types, unités et cardinalités des contrats JSON.
- Noms et types des colonnes SQL, clés étrangères, contraintes et vues.
- Conventions de temps, d'identifiants, de devise et d'idempotence.
- Sens des champs monétaires : `*_micros`, `accounting_unit`,
  `collateral_asset`, `settlement_asset`, `presentation_currency`.
- Séparation des sources Gamma / CLOB / Data API / temps réel.
- Structure du grand livre et invariants comptables.

Le gel ne couvre pas : les valeurs de frais, les endpoints exacts, les champs
amont, les paramètres de stratégie, les seuils de risque.

## 3. Règles de changement après gel

- Toute modification d'interface passe par A0, avec une nouvelle version
  (`schema_version` et/ou migration SQL).
- **Phase pré-gel (D-040)** : une extension compatible reste une version
  mineure. Une version mineure peut aussi contenir des changements
  incompatibles documentés, testés et accompagnés d'une déclaration de
  compatibilité. `1.1.0` n'est pas rétrocompatible avec `1.0.0` au sens de la
  validation ; les documents `1.0.0` restent des archives lisibles.
- **Après gel (SemVer strict)** : un changement de type, d'unité ou de
  sémantique, un retrait d'énumération ou un ajout de champ obligatoire est une
  version majeure. Un ajout de champ optionnel est une version mineure, avec
  test de compatibilité.
- Aucun agent ne modifie `contracts/` ou `schemas/` sans accord A0.
- Toute migration SQL est accompagnée d'une note de migration et d'un test de
  rejeu.
- Une modification après consultation du `final_test` crée une nouvelle
  expérience et, si possible, un nouveau test indépendant.

## 4. Découpage fixtures / réseau

| Domaine | Réalisable sur fixtures locales | Nécessite des données réseau |
|---|---|---|
| Contrats JSON et schéma SQL | Oui | Non |
| Normalisation des 7 types d'événements | Oui | Oui pour les champs amont réels |
| Génération déterministe des `event_id` | Oui | Non |
| Conversions Decimal → micros | Oui | Non |
| Stockage idempotent, dedup, timestamps | Oui | Non |
| Reconstruction de carnet à partir de snapshots/deltas | Oui | Oui pour la qualité réelle |
| Exécution taker, fills partiels, frais fictifs | Oui | Non |
| Grand livre et réconciliation | Oui | Non |
| Résolution et settlement | Oui | Oui pour les règles officielles |
| Dashboard en lecture seule | Oui | Oui pour le paper live |
| Tests de contrat, anti-look-ahead, idempotence | Oui | Non |
| Benchmarks indépendants | Oui sur fixtures | Oui pour des conclusions réelles |
| Mesure de latence et qualité de flux | Non | Oui |
| Sélection des traders | Non | Oui |

Règle : un résultat obtenu sur fixtures ne doit jamais être présenté comme une
preuve de performance ou comme un test réseau.

## 5. Critères d'acceptation par agent

### A1 — Collecte, normalisation, stockage, `core/`

**Fixtures locales (bloquant le gel) :**
- `core/units.py` : `to_micros(Decimal, decimals)` exact, arrondi explicite,
  tests de décimales, de valeurs négatives et de dépassement.
- `core/time.py` : timestamps UTC canoniques à six décimales, refus des offsets.
- `core/ids.py` : `deterministic_event_id` stable, test de collision et de
  rejeu.
- Normalisation des 7 types d'événements conforme au contrat, avec payload brut
  référencé et SHA-256.
- Ordre canonique des niveaux de carnet (bids décroissants, asks croissants).
- Stockage idempotent : double append, redémarrage, doublon
  `(source, source_event_id)`.
- Refus des timestamps non canoniques, prix hors `[0,1]`, sources inconnues,
  champs de type incohérent.
- Historisation des métadonnées de marché ; projection `markets` séparée.
- Manifeste de données : cutoff de réception, filtres (dont `sources`),
  SHA-256 recalculable.
- Incidents de qualité : trou, déconnexion, carnet incomplet, dérive d'horloge,
  doublon inter-sources.
- Tests SQL : contraintes, index uniques, triggers de type, foreign keys.

**Nécessite le réseau (non bloquant pour les fixtures) :**
- Un adaptateur par source (`gamma_api`, `clob_api`, `data_api`, `clob_ws`) avec
  endpoints, champs, unités et dates de consultation documentés.
- Aucun mapping générique entre sources ; `source_schema_version` renseigné.
- Reconnexion, rate limits, reprise et détection de trous.
- Dédup inter-sources sans fusion silencieuse.
- Aucun ordre réel, aucune clé privée d'ordre.

### A2 — Simulation et ledger

**Fixtures locales (bloquant le gel) :**
- Fonction d'exécution pure : achat sur asks croissants, vente sur bids
  décroissants, prix moyen pondéré.
- Fills partiels, reliquats, profondeur insuffisante, carnet périmé.
- Latence, haircut, profondeur maximale et ordre limite obligatoire.
- Frais via `FeeCalculator` avec un barème fictif explicitement `unverified`.
- Grand livre en partie double : somme nulle, cash ≥ 0, quantité ≥ 0, pas de
  short, pas de cash issu du PnL latent.
- Coût de revient, PnL réalisé, PnL latent, frais en collatéral. Les frais en
  parts sont différés avec Q-011 et ne font pas partie des critères V1.
- Résolution gagnante, perdante et VOID ; conversion pUSD → USDC par
  `conversion_rule` explicite.
- Idempotence : double `apply_fill`, double settlement, reversal.
- Aucune I/O réseau, aucune horloge murale, aucun LLM.

**Nécessite le réseau :**
- Aucun calcul cœur. L'intégration paper live consomme uniquement les
  événements déjà stockés par A1.

### A3 — Recherche et stratégies

**Fixtures locales :**
- Contrat d'hypothèse valide, séparation faits / hypothèse / inconnues / biais.
- Traduction de chaque règle en configuration déterministe versionnée.
- Aucun accès aux données postérieures à `decision_timestamp`.
- Paramètres figés et reproductibles ; aucun LLM dans la décision.
- Tests de non-régression sur les règles.

**Nécessite le réseau :**
- Sélection documentée des trois traders et analyse de leurs activités
  publiques.
- Gestion du biais du survivant, de la visibilité partielle et de
  l'incertitude maker/taker.
- Aucune conclusion de rentabilité sur un petit échantillon.

### A4 — Dashboard

**Fixtures locales (bloquant le gel) :**
- Lecture seule sur les vues et snapshots.
- Bannière « PAPER TRADING — AUCUN ARGENT RÉEL ».
- Affichage des données manquantes comme manquantes, sans interpolation.
- Statut des frais (`verified` / `provisional` / `unverified`).
- Incidents de qualité, latence, rejets et positions.
- Aucun recalcul du PnL fourni par le ledger.
- Aucun bouton ou endpoint d'ordre réel.

**Nécessite le réseau :**
- Branchement sur les données paper live d'A1/A2, toujours en lecture seule.

### A5 — Validation, benchmarks et audit

**Fixtures locales (bloquant le gel) :**
- Tests de contrat positifs et négatifs pour les 5 schémas.
- Test d'égalité des définitions `execution_assumptions` entre
  `execution.schema.json` et `experiment.schema.json`.
- Tests SQL : schéma neuf, STRICT, FK, CHECK, index uniques, triggers,
  vues d'audit.
- Tests comptables : somme nulle, cash, positions, frais, settlement,
  reversals.
- Tests d'idempotence : événement, fill, transaction.
- Tests anti-look-ahead : événement reçu après `T` invisible ; cutoff du
  manifeste.
- Test de reproductibilité : même seed, même manifeste, même configuration ⇒
  même résultat.
- Test de séparation des benchmarks : aucun import des décisions du bot évalué.
- Rapport des tests non exécutés.

**Nécessite le réseau :**
- Benchmark indépendant sur données réelles.
- Mesure de latence, qualité de flux et doublons inter-sources.
- Audit des biais sur les données réelles ; aucune conclusion définitive sur
  une courte période.

## 6. Tests qui doivent être commités avant le gel

- `tests/unit/test_contracts_*.py` : validation des schémas et exemples.
- `tests/unit/test_execution_assumptions_parity.py` : égalité des définitions.
- `tests/integration/test_schema_sqlite.py` : exécution du schéma, contraintes,
  triggers, vues.
- `tests/accounting/test_ledger_invariants.py` : somme nulle, cash, positions,
  frais, settlement, reversal.
- `tests/integration/test_idempotence.py` : double append, double fill, double
  transaction.
- `tests/integration/test_anti_lookahead.py` : cutoff et visibilité.
- `tests/unit/test_units_decimal.py` : conversions et arrondis.

A5 peut renommer ces fichiers, mais chaque catégorie doit exister et être
exécutable avec `pytest`.

## 7. Points bloquants ou à différer

**Bloquants avant gel :**
- D-025 (présente proposition) validée.
- Tests A5 §6 verts.
- Propriétaire de `core/` accepté par A1/A2 (D-017).
- Aucune modification ouverte de contrat.
- **C-01/C-02/C-03** vérifiés indépendamment par A5 : monotonie des chaînes de
  remplacement, horloge de stockage sans antidatage, seal de manifeste
  obligatoire. Ces règles sont candidates dans `0005` et les tests P0 ; elles
  ne sont pas gelées avant le rapport A5.
- Aucune migration `0005`/`0006`/`0007` exécutée sur la base de travail sans
  décision séparée du propriétaire.

**Différables, avec étiquette explicite :**
- Q-001 : source canonique token/outcome.
- Q-002 : politique de doublons inter-sources.
- Q-003 : frais prélevés en parts.
- Q-004 : positions ouvertes en fin d'expérience.
- Q-005 : manifeste en paper live.
- Q-006 : rétention des payloads.
- Q-007 : plage de versions Python.
- Q-008 : critères de sélection des traders.
- Q-009 : conversion pUSD → USDC à la résolution.

Un point différé ne bloque pas les fixtures, mais il interdit de présenter un
PnL net comme définitif s'il l'affecte.

## 8. Hors périmètre du gel

- Ordres réels et clés privées d'ordre.
- Ordres maker et file d'attente.
- Fonctions de transaction on-chain.
- Valeurs de frais, seuils de risque et paramètres de stratégie.
- Endpoints et champs amont exacts (documentés par A1).
- Choix des traders et conclusions de performance.

## 9. Ordre de lancement proposé

1. **A0** : prononce le gel après validation de ce document.
2. **A5** : committe les tests de contrat et de schéma, puis les maintient.
3. **A1** : fixtures, `core/`, normalisation, stockage, manifeste. Ensuite
   seulement, adaptateurs réseau après documentation des sources.
4. **A2** : exécution pure et ledger sur fixtures, en parallèle d'A1 une fois le
   gel prononcé.
5. **A3** : hypothèses et stratégies déterministes sur fixtures, puis analyse
   réseau.
6. **A4** : dashboard sur fixtures, puis branchement lecture seule.
7. **A5** : benchmarks et audit sur données réelles en dernier.

Aucun agent ne démarre avant que le gel soit prononcé, sauf A5 pour préparer les
tests et A1 pour les fixtures explicitement autorisées.

## 10. Enregistrement des vérifications

| Date | Vérification | Résultat |
|---|---|---|
| 2026-10-26 | Schémas JSON et exemples | 5 schémas, 14 exemples, 0 échec |
| 2026-10-26 | Cas négatifs JSON | 62 assertions PASS |
| 2026-10-26 | Schéma SQL et contraintes | 26 tables, 7 vues, 13 triggers, 18 index ; 24 assertions PASS |
| 2026-10-26 | Cohérence `event_type` | PASS sur contrat, filtre d'expérience et SQL |
| 2026-10-26 | Vérification documentaire Polymarket | Rapportée par le propriétaire, non rejouée par A0 |
| 2026-10-27 | Suite A5 après corrections SQL — **mesure historique antérieure à B-04/P0** | 472 tests collectés, 470 PASS, 2 xfail documentés (A5-06), 0 échec inattendu |
| 2026-10-27 | Suite après corrections A5-REAUDIT — **mesure historique avant A5-06** | 600 tests collectés, 598 PASS, 2 xfail A5-06, 0 échec inattendu |
| 2026-10-27 | Suite après correction A5-06 (D-050) — **historique avant 0007** | 619 tests collectés, 619 PASS, 0 xfail, 0 échec inattendu |
| 2026-10-27 | Suite après alignement contrats/SQL (D-051) — **historique avant writer** | 639 tests collectés, 639 PASS, 0 xfail, 0 échec inattendu |
| 2026-10-27 | Suite après intégration du writer (D-052) — **historique avant durcissement** | 653 tests collectés, 653 PASS, 0 xfail, 0 échec inattendu |
| 2026-10-27 | Suite après durcissement du writer (D-053) — historique | 672 tests collectés, 672 PASS, 0 xfail, 0 échec inattendu |
| 2026-10-27 | Suite après fermeture des contournements (D-054) | 717 tests collectés, 717 PASS, 0 xfail, 0 échec inattendu |
| 2026-10-27 | Suite après corrections A5-C2 (D-055) | 744 tests collectés, 744 PASS, 0 xfail, 0 échec inattendu |
| 2026-10-27 | Schéma SQL `0.3` | 26 tables, 7 vues, 39 triggers, 18 index ; `user_version = 3` |
| 2026-10-27 | Intégrité SQLite sur base seedée + réouverture | `integrity_check = ok`, `foreign_key_check` vide, WAL actif |
| — | Test réseau Polymarket | **Non exécuté** |
