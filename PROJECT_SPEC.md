# PROJECT_SPEC.md
# Polymarket Strategy Research Lab — Spécification du projet

**Version :** 0.1 — cadrage initial  
**Statut :** document de référence évolutif  
**Environnement cible initial :** Windows local  
**Mode financier :** paper trading uniquement, aucun ordre réel

## 1. Vision

Construire un laboratoire de recherche local permettant d'évaluer si des comportements observés chez trois traders performants sur Polymarket peuvent être transformés en stratégies reproductibles, après prise en compte des coûts et contraintes d'exécution.

Le système doit observer en priorité les traders actifs sur les marchés crypto à court terme. Il doit collecter les données disponibles, analyser les comportements, produire des stratégies candidates, les simuler, les comparer à des benchmarks indépendants et visualiser les résultats dans un dashboard.

## 2. Questions de recherche

1. Quels comportements récurrents peut-on observer dans les transactions publiques de trois traders sélectionnés ?
2. Quelles hypothèses de stratégie sont suffisamment étayées pour être testées ?
3. Les résultats simulés restent-ils positifs après spread, frais, slippage, latence et profondeur observable ?
4. La stratégie résiste-t-elle à des hypothèses d'exécution plus défavorables ?
5. Les résultats se maintiennent-ils sur des périodes distinctes et en paper trading en direct ?
6. Les performances dépassent-elles celles de benchmarks définis à l'avance ?

## 3. Périmètre de la première version

### Inclus
- Sélection et suivi de **3 traders**.
- Focus initial sur les marchés **crypto**.
- Collecte des données publiques accessibles et autorisées.
- Enregistrement local des événements et snapshots de carnet disponibles.
- Analyse assistée par IA, avec séparation entre faits, hypothèses et inconnues.
- Stratégies candidates versionnées et configurables.
- Paper trading avec **ordres taker seulement** dans la première version.
- Calcul d'exécution à partir de la profondeur observable, avec hypothèses de latence et d'évolution du carnet.
- Modèle de frais configurable et daté, basé sur les règles applicables au marché et au moment concernés.
- Capital virtuel testé sur une plage de **100 à 10 000 USDC/USD**, avec scénarios de taille prédéfinis.
- Dashboard local : performance, positions, transactions, carnet, comparaison avec le trader.
- Validation technique, historique et en direct.
- Module de benchmark indépendant des stratégies évaluées.
- Journaux, rapports d'expériences et versionnage de configurations.

### Exclu de la première version
- Passage d'ordres avec argent réel.
- Ordres maker et modélisation de file d'attente.
- Autres catégories que crypto, sauf extension ultérieure.
- Déploiement VPS comme environnement principal.
- Promesse de rentabilité ou conseil financier.
- Automatisation de décisions de trading par un LLM à chaque tick.

## 4. Principes de conception

1. **Paper-only par défaut :** aucun chemin d'exécution réel ne doit être présent dans la V1.
2. **Calculs déterministes :** le code, et non le LLM, calcule PnL, frais, exposition et métriques.
3. **Pas de look-ahead :** une décision ne peut utiliser que les informations disponibles à son horodatage.
4. **Traçabilité :** chaque décision doit être reliée à la donnée, à la version de stratégie et aux hypothèses de simulation.
5. **Reproductibilité :** une expérience doit pouvoir être rejouée avec la même version des données et de la configuration.
6. **Incertitude explicite :** distinguer données observées, estimations, hypothèses et informations inconnues.
7. **Benchmark indépendant :** les benchmarks utilisent les mêmes fenêtres temporelles, contraintes de capital et conventions de coûts.
8. **Architecture extensible :** prévoir une interface d'exécution permettant d'ajouter plus tard les ordres maker sans réécrire les stratégies.
9. **Tolérance aux pannes :** reconnecter les flux, détecter les trous de données et marquer les périodes incomplètes.
10. **Aucune fuite de secrets :** aucune clé API privée ni donnée sensible dans les logs ou le dépôt.

## 5. Utilisateurs et rôles

- **Propriétaire / chercheur :** choisit les traders, valide les hypothèses, examine les rapports.
- **Agents de développement :** construisent des composants distincts selon leurs responsabilités.
- **Agent d'analyse des traders :** produit des hypothèses à partir des données publiques.
- **Agent de validation :** cherche les erreurs de calcul, biais et résultats suspects.
- **Système logiciel :** collecte, simule, comptabilise et affiche les données de façon déterministe.

## 6. Définition du succès de la V1

La V1 est considérée techniquement prête lorsque :
- les données sont horodatées et leur qualité est mesurée ;
- les ordres taker simulés consomment les niveaux du carnet dans l'ordre de prix ;
- les quantités simulées ne dépassent pas la liquidité supposée disponible ;
- frais, latence, spread et slippage sont visibles séparément ;
- le grand livre du portefeuille se réconcilie ;
- les tests techniques sont verts ;
- les tests historiques n'utilisent aucune information future ;
- le paper trading en direct produit un journal d'audit ;
- les benchmarks sont exécutés indépendamment ;
- le dashboard compare les stratégies avec les mêmes conventions de calcul.

Une stratégie ne sera pas déclarée « fiable » sur la seule base de quelques gains. La conclusion doit tenir compte du nombre d'observations, de l'incertitude, des drawdowns, de la concentration des gains, des coûts et des performances hors échantillon.

## 7. Hypothèses et limites

- Les données publiques ne révèlent pas nécessairement les intentions, ordres non exécutés, annulations ou l'intégralité du portefeuille du trader.
- Les transactions visibles ne permettent pas toujours d'identifier avec certitude le caractère maker/taker.
- Un snapshot de carnet ne garantit pas que la liquidité restera disponible après la latence.
- La simulation de la profondeur historique n'est fiable que si des données historiques adéquates du carnet existent.
- Les résultats de paper trading ne sont pas identiques à des exécutions réelles.
- Les frais, interfaces et règles de marché peuvent évoluer ; les paramètres doivent être datés et vérifiés.

## 8. Décisions à confirmer au cours du développement

- Trois traders précis, sélectionnés selon des critères documentés.
- Fenêtre historique disponible et fréquence de collecte.
- Devise comptable de référence (USD ou USDC) et conventions de conversion.
- Durées exactes des fenêtres de recherche, validation et test final.
- Seuils de risque, taille maximale des positions et limites par marché.
- Politique de traitement des données manquantes.
- Durée minimale du paper trading avant revue.

## 9. Hors objectif

Le projet est un outil de recherche et d'expérimentation. Il ne garantit ni la rentabilité future, ni la possibilité de copier fidèlement un trader. Il ne doit pas être utilisé pour prendre automatiquement des positions réelles dans sa première version.
