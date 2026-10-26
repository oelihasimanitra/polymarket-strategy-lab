# VALIDATION_PLAN.md
# Polymarket Strategy Research Lab — Plan de validation et benchmarks

**Version :** 0.1  
**Objet :** éviter les erreurs techniques et les conclusions statistiques trop optimistes.

## 1. Trois couches de validation

### A. Validation technique
Vérifie que le système collecte, traite et comptabilise correctement les données.

### B. Validation historique
Vérifie si une stratégie aurait obtenu des résultats plausibles sur une période passée, sans fuite d'information future.

### C. Validation en direct (paper trading)
Vérifie si les résultats se maintiennent sur des données nouvelles et des conditions de marché réelles, sans argent réel.

Ces couches sont complémentaires. Réussir une couche ne garantit pas la réussite des autres.

## 2. Validation technique — critères d'acceptation

### Données
- Les timestamps source et réception sont conservés.
- Les événements dupliqués sont détectés.
- Les trous de flux et déconnexions sont journalisés.
- Les données périmées ne déclenchent pas silencieusement de simulation.
- Les payloads bruts utiles sont conservés ou référencés.

### Carnet et exécution
- Un achat consomme les asks dans l'ordre croissant des prix.
- Une vente consomme les bids dans l'ordre décroissant.
- Les quantités exécutées ne dépassent pas la liquidité retenue par le modèle.
- Les fills partiels et reliquats sont gérés.
- Le prix moyen pondéré est correct.
- Les frais et conventions sont attachés à chaque fill.
- Les ordres sont idempotents et ne sont pas comptabilisés deux fois.

### Comptabilité
- Le cash et les positions se réconcilient après chaque fill.
- Le PnL réalisé et latent sont séparés.
- Les frais réduisent le résultat conformément au modèle.
- La valorisation d'une position utilise la convention annoncée.
- Les limites de capital et de risque sont appliquées.

### Stratégies
- Une stratégie ne voit que les événements disponibles à son instant de décision.
- Les paramètres sont versionnés.
- Un run peut être rejoué.
- Le résultat ne dépend pas de l'ordre d'exécution non déterministe des tâches.

## 3. Tests historiques

### Séparation temporelle
Définir avant l'analyse :
1. période de recherche / développement ;
2. période de validation ;
3. période de test final non consultée pendant le réglage.

Les périodes doivent être chronologiques et, autant que possible, non chevauchantes. La période de test final ne doit pas être réutilisée pour choisir des paramètres.

### Méthode
- Rejouer les événements dans l'ordre temporel.
- N'utiliser que les données connues au moment de chaque décision.
- Appliquer les délais de détection et d'exécution.
- Signaler l'absence de carnet historique adéquat.
- Ne pas simuler une exécution précise si seules des données de prix sont disponibles.
- Calculer les résultats avec le même moteur de PnL que le paper trading.
- Enregistrer toutes les variantes testées pour rendre visible le risque de surapprentissage.

### Métriques
- PnL net et brut ;
- rendement sur capital ;
- drawdown maximal ;
- profit factor ;
- taux de réussite, accompagné du gain/perte moyen ;
- nombre de transactions ;
- frais, spread et slippage estimés ;
- exposition maximale ;
- concentration des gains ;
- résultats par jour/semaine et par régime de marché ;
- incertitude statistique et taille d'échantillon.

## 4. Validation en direct

- Démarrer sans argent réel.
- Exécuter les bots sur les mêmes flux de marché.
- Consigner les données reçues, décisions, latences et exécutions simulées.
- Comparer les prix du trader, les prix observés à la réception et les prix estimés exécutables.
- Mesurer la proportion de décisions rejetées à cause de données périmées ou d'une profondeur insuffisante.
- Comparer le PnL direct avec le résultat historique attendu.
- Réaliser des revues régulières des erreurs et des écarts.
- Ne pas déclarer la stratégie fiable sur la base d'une courte période ou d'un petit nombre de trades.

## 5. Benchmark Engine indépendant

Le moteur de benchmark doit être un module séparé. Il reçoit les mêmes données et conventions, mais ne dépend pas des décisions internes du bot évalué.

### Benchmarks initiaux
1. **Copie différée du trader** : reproduit les signaux observables après un délai paramétrable.
2. **Contrôle sans signal** : stratégie de référence simple, clairement définie, avec les mêmes limites de risque.
3. **Baseline passive** : uniquement si une référence passive économiquement pertinente existe pour le marché étudié.
4. **Contrôle aléatoire contraint** : extension ultérieure, avec mêmes fréquences/expositions et sans accès au futur.

### Garanties de comparaison
- mêmes fenêtres temporelles ;
- mêmes hypothèses de capital ;
- mêmes limites de position ;
- mêmes conventions de frais et de valorisation ;
- même moteur de métriques ;
- paramètres du benchmark définis avant le test final ;
- rapport des écarts et limites.

## 6. Stress tests

Tester au minimum :
- latence faible, centrale et élevée ;
- liquidité réduite par rapport au snapshot ;
- spread plus large ;
- frais selon le barème vérifié et scénario de coût défavorable si pertinent ;
- flux interrompu ou données périmées ;
- exécutions partielles ;
- taille de capital de 100 à 10 000 ;
- variation des paramètres dans une plage raisonnable ;
- marchés très volatils et marchés peu actifs.

Les stress tests sont des scénarios, pas des prévisions.

## 7. Critères d'une stratégie candidate à approfondir

Aucune règle universelle ne suffit pour certifier la fiabilité. Une stratégie mérite un examen supplémentaire si :
- les tests techniques passent ;
- les données sont suffisamment complètes pour le type de stratégie ;
- la performance reste cohérente après les coûts ;
- les résultats ne dépendent pas d'une ou deux transactions ;
- le drawdown est compris et acceptable selon des seuils définis avant le test ;
- la performance hors échantillon n'est pas incompatible avec celle de recherche ;
- les résultats en direct sont cohérents avec les hypothèses de simulation ;
- les benchmarks sont dépassés avec une marge qui ne semble pas uniquement due au hasard ;
- l'incertitude et les limites sont documentées.

Une performance positive ne constitue pas une garantie de résultats futurs.

## 8. Rapports obligatoires par expérience

Chaque rapport doit inclure :
- identifiant de l'expérience ;
- trader et stratégie ;
- versions du code et de configuration ;
- période et qualité des données ;
- hypothèses de latence, frais, spread et liquidité ;
- capital et limites de risque ;
- métriques et courbes ;
- comparaison aux benchmarks ;
- tests de sensibilité ;
- anomalies ;
- conclusion prudente ;
- décision : poursuivre, modifier, suspendre ou abandonner.

## 9. Revue et gouvernance
- Les changements de stratégie sont versionnés.
- Un changement après consultation du test final entraîne la création d'une nouvelle expérience et d'un nouveau test indépendant si possible.
- L'agent de validation doit pouvoir contester une conclusion de rentabilité.
- Les rapports distinguent clairement simulation, estimation et observation.
