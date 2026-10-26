# Contrats de données — version 1.0.0 (proposition A0)

Statut : **PROPOSITION**, non gelée. Les décisions D-009 à D-024 sont approuvées
en principe le 2026-10-26 ; le gel formel est proposé dans
`CONTRACT_FREEZE_PROPOSAL.md`.

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
- **`schema_version`** : chaque document persisté porte sa version. Le passage
  à une version majeure est une rupture de contrat, pas un simple ajout.

## Fichiers

| Fichier | Objet | Consommateurs |
|---|---|---|
| `market_event.schema.json` | Événement de marché normalisé : trade, carnet, delta, activité trader, métadonnées, résolution, connexion | A1, A2, A5 |
| `execution.schema.json` | `order_intent`, `execution_assumptions`, `execution_estimate`, `fill`, `execution_result` | A2, A5 |
| `fee_schedule.schema.json` | Barème de frais daté, sourcé et versionné | A1, A2, A5 |
| `experiment.schema.json` | Enveloppe de reproductibilité d'une expérience | A2, A3, A5 |
| `strategy_hypothesis.schema.json` | Hypothèse traçable ; les règles textuelles ne sont pas exécutables | A3, A5 |
| `CONTRACT_FREEZE_PROPOSAL.md` | Proposition de gel et critères d'acceptation A1–A5, séparés fixtures / réseau | A0, tous |

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
