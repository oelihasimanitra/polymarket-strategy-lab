# Contrats de données — candidat 1.2.0 (proposition A0)

Statut : **CANDIDAT NON GELÉ**. Les versions `1.1.0` (contrats) et `0.4`
(SQL) restent les références auditées. Les contrats `market_event`,
`execution`, `experiment` et `fee_schedule` en `1.2.0` et les migrations
candidates `0005`/`0006` sont préparés mais **non approuvés et non exécutés**.
Les décisions D-009 à D-024 sont approuvées en principe le 2026-10-26 ; D-027 à
D-050 sont préparées, avec les réserves indiquées dans `DECISIONS.md`. Le gel
formel est proposé dans `CONTRACT_FREEZE_PROPOSAL.md`.

## Conventions communes

- **Montants, prix, tailles** : entiers en micro-unités, échelle 1e-6.
  - montant / cash / frais / PnL : micro-unités de l'**unité comptable**
    (`accounting_unit`) ;
  - prix : micro-probabilité (1 000 000 = 1.00) ;
  - taille : micro-parts (1 000 000 = 1 part).
- **Timestamps** : UTC canonique, exactement six décimales, suffixe `Z` :
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`. Les offsets (`+00:00`) sont refusés.
- **Trois niveaux monétaires distincts** : actif de collatéral
  (`collateral_asset`), unité comptable (`accounting_unit`), actif de règlement
  (`settlement_asset`), plus la devise de présentation
  (`presentation_currency`). Aucune conversion implicite, même 1:1.
- **Sources distinctes** : `gamma_api`, `clob_api`, `data_api`, `clob_ws`,
  `fixture`. Les champs ne sont pas interchangeables ; chaque adaptateur
  normalise son propre schéma.
- **JSON strict** : `additionalProperties: false`. Tout champ nouveau exige une
  nouvelle version de contrat.
- **Chronologie (A5-06)** : JSON Schema 2020-12 ne compare pas deux champs.
  Les schémas `fee_schedule` et `experiment` déclarent donc l'extension
  normative `x-polymarket-chronological-order` : `end_field` doit être
  **strictement** postérieur à `start_field`, une fin nulle est admise, et
  l'absence d'une fin n'est admise que si le champ n'est pas requis par le
  schéma (`fee_schedule.effective_to`). Un validateur JSON Schema standard
  ignore cette extension : tout consommateur **DOIT** l'implémenter et
  l'appliquer avant insertion. Le point d'entrée applicatif est
  `src/polymarket_lab/validation/contracts.py::validate_contract` ; il applique
  le validateur JSON Schema fourni puis l'extension chronologique.
- **Registre de production** : `src/polymarket_lab/validation/registry.py`
  épingle le nom, la version et le SHA-256 des schémas `experiment` et
  `fee_schedule`. La vue publique est en lecture seule ; le writer relit une
  donnée privée à chaque écriture, vérifie le hash et construit lui-même le
  validateur à partir du schéma gelé. Aucun schéma ni validateur fourni par
  l'appelant n'est accepté par le parcours normal. Les schémas temporaires de
  test passent par `storage.contract_writer_testing`.
- **`schema_version`** : chaque document persisté porte sa version.
- **Phase pré-gel (D-040)** : les contrats ne sont pas encore des interfaces
  stables et aucun consommateur externe ne les utilise. Une extension
  compatible reste une version mineure. Une version mineure peut aussi
  contenir des changements incompatibles, à condition qu'ils soient documentés,
  testés et accompagnés d'une déclaration de compatibilité.
- **Après gel (SemVer strict)** : un ajout de champ optionnel est une version
  mineure ; un changement de type, d'unité ou de sémantique, un retrait
  d'énumération ou un ajout de champ obligatoire est une version majeure.
- **Version 1.1.0** : ajoute des champs obligatoires (`normalizer_version`,
  `trader_visibility`, `order_id` dans `execution_estimate`,
  `rounding_increment_micros`) et retire les valeurs suspendues en V1
  (`per_share`, `custom`, `outcome_token`, `not_required`, latence `normal`).
  **Compatibilité déclarée** : les documents 1.0.0 restent des archives
  lisibles, mais ne valident pas le schéma 1.1.0 ; aucun producteur 1.0.0 n'est
  compatible sans migration. Cette rupture pré-gel est assumée par D-040.
- **Candidat 1.2.0** : `market_event`, `execution`, `experiment` et
  `fee_schedule` passent à `1.2.0`. `market_event`, `execution` et `experiment`
  ajoutent `event_identity_version='v2'`, l'ancrage `source_event_id` ou
  `raw_payload_sha256`, `rng_implementation='polymarket-lab/rng/v2'` et
  `config_hash_version='config/v2'`. `latency_distribution='fixed'` impose
  `latency_jitter_ms=0` ; le seed est borné à `2^63-1`. `fee_schedule` passe à
  `1.2.0` pour porter l'extension chronologique A5-06 ; `strategy_hypothesis`
  reste `1.0.0`.
- **Identité v2 des exemples** : les `event_id` des exemples de marché sont
  recalculés avec `event-id/v2` ; les références `book_snapshot_event_id` sont
  alignées.
- **Suspensions V1** : frais `per_share` et `outcome_token`, formule `custom`,
  statut de frais `not_required`, latence `normal`, règlement `VOID` sans règle
  sourcée. Q-010 à Q-012 restent ouvertes.

## Fichiers

| Fichier | Objet | Consommateurs |
|---|---|---|
| `market_event.schema.json` | Événement de marché normalisé : trade, carnet, delta, activité trader, métadonnées, résolution, connexion | A1, A2, A5 |
| `execution.schema.json` | `order_intent`, `execution_assumptions`, `execution_estimate`, `fill`, `execution_result` | A2, A5 |
| `fee_schedule.schema.json` | Barème de frais daté, sourcé et versionné | A1, A2, A5 |
| `experiment.schema.json` | Enveloppe de reproductibilité d'une expérience | A2, A3, A5 |
| `strategy_hypothesis.schema.json` | Hypothèse traçable ; les règles textuelles ne sont pas exécutables | A3, A5 |
| `CONTRACT_FREEZE_PROPOSAL.md` | Proposition de gel et critères d'acceptation A1–A5, séparés fixtures / réseau | A0, tous |
| `../WRITER_INTEGRATION.md` | Interface commune des writers A1/A2 et règles de validation | A1, A2, A5 |

`execution.schema.json` et `experiment.schema.json` définissent tous deux
`execution_assumptions`. La duplication est volontaire pour permettre une
validation autonome de chaque fichier. **A5 doit tester que les deux
définitions ont les mêmes propriétés et les mêmes champs requis.**

## Exemples

Les fichiers de `examples/` sont **fictifs**. Ils ne représentent aucun trader,
aucun marché et aucun barème Polymarket réel. Le barème d'exemple est marqué
`unverified` et pointe vers `example.invalid`. Les exemples utilisent `pUSD`
comme actif de collatéral et `USDC` comme actif de règlement pour illustrer la
séparation ; la règle de conversion d'exemple est explicitement `unverified`.

## Validation

Depuis la racine du dépôt, avec l'environnement virtuel du projet :

```powershell
.\.venv\Scripts\python.exe -c "import json,pathlib; from jsonschema import Draft202012Validator as V; [V.check_schema(json.loads(p.read_text(encoding='utf-8'))) for p in pathlib.Path('contracts').glob('*.schema.json')]; print('schemas ok')"
```

Les tests de contrat complets (exemples positifs, cas négatifs, égalité des
définitions `execution_assumptions`) doivent être commités par A5 dans
`tests/unit/` et `tests/integration/`. A0 ne les a pas commités : `tests/` est
hors de son périmètre.

## Points non vérifiés

Aucun endpoint, champ Polymarket ou taux de frais n'est affirmé dans ces
contrats. La liste des vérifications documentaires obligatoires est dans
`ARCHITECTURE.md`, section « Points Polymarket à vérifier ». Une fixture ne
prouve jamais qu'un barème est valide.
