# ARCHITECTURE.md
# Polymarket Strategy Research Lab — Architecture technique

**Version :** 0.1  
**Cible :** PC Windows, développement local  
**Principe :** monolithe modulaire au départ, composants séparables ensuite

## 1. Vue d'ensemble

```text
Polymarket public data / market WebSocket
                 |
                 v
        [1. Data Collectors]
                 |
                 v
      [2. Normalization & Quality]
                 |
                 v
       [3. Local Data Store]
                 |
       +---------+----------+
       |                    |
       v                    v
[4. Trader Analytics] [5. Market State]
       |                    |
       v                    |
[6. Strategy Registry]      |
       |                    |
       +---------+----------+
                 v
       [7. Simulation Engine]
                 |
        +--------+--------+
        |        |        |
        v        v        v
      Bot A    Bot B    Bot C
                 |
                 v
       [8. Ledger & Metrics]
                 |
          +------+------+
          |             |
          v             v
 [9. Benchmark Engine] [10. Dashboard]
          |             |
          +------+------+
                 v
       [11. Validation & Reports]
```

## 2. Modules et contrats

### 2.1 Data Collectors
Responsabilités :
- Interroger les interfaces publiques documentées pour leaderboard, activité, transactions, marchés et positions, selon disponibilité.
- Consommer les flux de marché en temps réel pour les prix et carnets.
- Enregistrer les timestamps source et réception.
- Gérer reconnexion, limitation de débit, reprise et détection de trous.

Ne doit pas :
- inventer les données manquantes ;
- traiter une transaction observée comme une preuve complète de la stratégie ;
- envoyer des ordres réels.

### 2.2 Normalization & Data Quality
Responsabilités :
- normaliser les identifiants, timestamps, prix, quantités et marchés ;
- dédupliquer les événements ;
- vérifier les champs requis ;
- signaler les timestamps incohérents, données tardives et trous de flux ;
- attribuer un indicateur de qualité aux périodes.

### 2.3 Local Data Store
Choix de démarrage :
- SQLite pour un prototype à faible complexité ; ou PostgreSQL si le volume et les requêtes concurrentes le justifient.
- Stockage brut immuable des événements si possible.
- Tables normalisées pour marchés, traders, transactions, snapshots de carnet, stratégies, ordres simulés, fills, positions, expériences et métriques.

Évolution possible :
- PostgreSQL + TimescaleDB pour séries temporelles.
- Export Parquet pour analyses historiques.
- Pas de dépendance obligatoire à un VPS pour la V1.

### 2.4 Trader Analytics
Produit des rapports qui séparent :
- faits observés ;
- hypothèses de comportement ;
- inconnues ;
- niveau de confiance et limites ;
- expérience proposée pour tester chaque hypothèse.

Les rapports IA ne modifient jamais directement le grand livre ou les calculs de PnL.

### 2.5 Strategy Registry
Chaque stratégie est identifiée par :
- `strategy_id`
- `version`
- `source_trader_id` éventuel
- configuration sérialisée
- date de création
- hypothèse testée
- périodes d'entraînement/validation/test
- statut (draft, backtest, paper, retired)

Une stratégie est une fonction de décision déterministe alimentée par des événements horodatés. Les appels LLM ne doivent pas se trouver dans le chemin critique de décision de la V1.

### 2.6 Simulation Engine
Interface d'exécution à prévoir dès la V1 :
- `submit_order`
- `estimate_execution`
- `cancel_order` (pour l'architecture future ; pas nécessaire à l'exécution maker de la V1)
- `apply_fill`
- `mark_to_market`

V1 :
- ordres taker uniquement ;
- consomme les niveaux du carnet du côté opposé ;
- applique un modèle de latence ;
- vérifie que le snapshot n'est pas trop ancien ;
- réévalue la liquidité disponible après latence selon un modèle explicitement choisi ;
- permet une exécution partielle ou un reliquat non exécuté ;
- applique les frais applicables et les règles de quantité/tick size ;
- enregistre chaque hypothèse d'exécution.

Future V2 :
- ordres maker ;
- modèle de file d'attente et de probabilité de fill ;
- annulations, priorité temporelle et risque d'adverse selection.

### 2.7 Ledger & Metrics
Le grand livre est la source de vérité pour :
- cash disponible ;
- parts détenues par token/résultat ;
- coût d'entrée ;
- frais ;
- PnL réalisé et latent ;
- capital immobilisé ;
- exposition et limites de risque.

Le PnL est calculé par du code testé, jamais par un LLM. Les conventions de valorisation sont versionnées et documentées.

### 2.8 Benchmark Engine — indépendant
Le moteur de benchmark est un module distinct des stratégies testées. Il reçoit le même flux de données, les mêmes fenêtres temporelles, les mêmes conventions de capital et de coûts.

Benchmarks initiaux :
1. **Copie différée** : signal issu des transactions observées du trader, avec latence paramétrable.
2. **Référence sans signal** : comportement de contrôle simple et documenté, soumis aux mêmes limites de risque.
3. **Baseline passive** : seulement lorsqu'une comparaison économiquement pertinente existe pour le marché considéré.
4. **Permutation / contrôle aléatoire contraint** : option ultérieure ; mêmes contraintes d'exposition et de fréquence, sans accès au futur.

Le benchmark ne doit pas importer les décisions internes du bot testé, ni être optimisé avec la période de test finale. Les résultats doivent être produits avec le même calculateur de métriques.

### 2.9 Dashboard
Vues :
- synthèse multi-bots ;
- performance et drawdown ;
- positions ouvertes ;
- historique des ordres/fills ;
- carnet et spread ;
- coûts estimés ;
- comparaison trader original vs bot ;
- état des flux et qualité des données ;
- résultats de validation et benchmarks.

Le dashboard est en lecture seule pour le moteur de simulation en V1, sauf actions de contrôle sans effet financier (pause/reprise des bots virtuels).

### 2.10 Validation & Reports
- tests unitaires et d'intégration ;
- tests comptables ;
- tests anti-look-ahead ;
- tests de robustesse aux coûts/latence ;
- comparaison historique et paper trading ;
- rapport de qualité des données ;
- rapport de reproductibilité.

## 3. Stack de départ recommandée

- Python 3.x, version supportée et verrouillée dans l'environnement.
- `asyncio` et WebSocket pour les flux.
- API/SDK officiel ou compatible, vérifié au démarrage du développement.
- `pandas`, `numpy`, `scipy` pour analyse.
- `pytest` pour tests.
- Streamlit + Plotly pour dashboard local.
- SQLite pour prototype ; PostgreSQL si les besoins l'imposent.
- `pyproject.toml` ou fichier de dépendances verrouillées.
- Git pour versionner code, configurations et documents.

Les interfaces Polymarket et les paramètres de frais doivent être vérifiés dans la documentation officielle au moment de l'implémentation. Les noms d'endpoint et formats de réponse peuvent évoluer.

## 4. Flux d'événement canonique

Chaque événement de marché devrait inclure, lorsque disponible :
- `event_id`
- `event_type`
- `market_id`
- `token_id`
- `source_timestamp`
- `received_timestamp`
- `sequence_number` ou identifiant source
- `price`
- `size`
- `side`
- `raw_payload_ref`
- `data_quality_flags`

Conserver les valeurs brutes utiles permet de corriger ultérieurement le parseur sans perdre la source.

## 5. Séparation des périodes

Chaque expérience doit référencer trois fenêtres non chevauchantes autant que possible :
- **Recherche / développement** : exploration et réglage.
- **Validation** : choix entre variantes et contrôle de stabilité.
- **Test final** : période tenue à l'écart jusqu'à la décision finale.

Pour les stratégies intrajournalières, les séparations doivent respecter l'ordre chronologique. Toute optimisation répétée sur le test final invalide son statut de test indépendant.

## 6. Déploiement local Windows

Démarrage :
1. environnement virtuel Python ;
2. configuration locale sans secrets ;
3. base locale ;
4. collecteur ;
5. simulateur ;
6. dashboard.

Prévoir un fichier `.env.example`, mais ne jamais committer le `.env` réel. Le mode paper doit être explicite et verrouillé. Aucune clé d'ordres réels ne doit être requise dans la V1.

## 7. Structure de dépôt suggérée

```text
polymarket-strategy-lab/
├── README.md
├── PROJECT_SPEC.md
├── ARCHITECTURE.md
├── SIMULATION_RULES.md
├── VALIDATION_PLAN.md
├── pyproject.toml
├── .env.example
├── configs/
│   ├── app.example.yaml
│   ├── traders.yaml
│   └── strategies/
├── src/
│   └── polymarket_lab/
│       ├── collectors/
│       ├── normalization/
│       ├── storage/
│       ├── analytics/
│       ├── strategies/
│       ├── simulation/
│       ├── ledger/
│       ├── benchmarks/
│       ├── validation/
│       └── dashboard/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── accounting/
│   └── fixtures/
├── data/              # local only; normally excluded from Git
├── reports/
└── logs/              # local only; normally excluded from Git
```

## 8. Principes de coordination des agents

Avant le travail en parallèle :
- l'architecte publie les interfaces, modèles de données et critères d'acceptation ;
- chaque agent possède un périmètre exclusif ;
- les agents ne modifient pas simultanément les mêmes fichiers ;
- toute interface change via une proposition et un test ;
- les agents livrent tests, documentation et limites connues avec le code ;
- l'agent validation peut bloquer un composant si les invariants ne sont pas respectés.
