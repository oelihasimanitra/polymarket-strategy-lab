# SIMULATION_RULES.md
# Polymarket Strategy Research Lab — Règles de simulation

**Version :** 0.1  
**V1 :** paper trading, ordres taker uniquement  
**But :** rendre explicites les hypothèses de coûts et d'exécution.

## 1. Principes non négociables

- Aucun ordre réel ne doit être envoyé.
- Une décision utilise uniquement les informations disponibles à l'heure de décision.
- Toute simulation conserve l'heure source, l'heure de réception, l'heure de décision et l'heure simulée d'exécution.
- Les prix et quantités proviennent de données observées ou d'hypothèses identifiées comme telles.
- Une donnée manquante ne doit pas être remplacée silencieusement par une valeur inventée.
- Les calculs financiers sont déterministes et couverts par des tests.
- Chaque expérience stocke les versions du code, de la stratégie, des données et du modèle de frais.

## 2. Types d'ordre dans la V1

### Inclus : taker / ordre immédiatement exécutable
Le simulateur estime l'exécution en consommant les niveaux disponibles du côté opposé du carnet, dans l'ordre des prix, après prise en compte de la latence modélisée.

### Exclu : maker
Les ordres maker sont réservés à une version ultérieure. Leur simulation devra modéliser au minimum la position dans la file, les quantités devant l'ordre, les transactions et annulations observées, les fills partiels et le risque d'adverse selection.

## 3. Latence et vieillissement du carnet

Pour chaque décision :
1. enregistrer le dernier snapshot connu et son âge ;
2. appliquer une latence simulée configurable ;
3. vérifier si le snapshot dépasse le seuil d'âge autorisé ;
4. estimer l'état exécutable à l'arrivée de l'ordre ;
5. exécuter uniquement sur la liquidité supposée disponible dans ce modèle ;
6. enregistrer la méthode d'estimation et son incertitude.

Trois modes de test sont recommandés :
- **optimiste encadré** : latence faible et snapshot récent ;
- **central** : latence mesurée par le système et règles de vieillissement documentées ;
- **stress** : latence plus longue, spread plus large et liquidité réduite.

Le mode central ne doit pas être présenté comme une vérité exacte. Le carnet peut changer entre le snapshot et l'arrivée de l'ordre. Si aucune observation ne permet de reconstruire le carnet à l'arrivée, l'exécution reste une estimation.

## 4. Consommation de la profondeur

Pour un achat, parcourir les asks du meilleur au moins bon prix ; pour une vente, parcourir les bids du meilleur au moins bon prix.

Pour chaque niveau :
- prendre le minimum entre la quantité restante et la quantité supposée disponible ;
- calculer le coût ou le produit de vente ;
- passer au niveau suivant si nécessaire ;
- arrêter lorsque la quantité est exécutée ou que la profondeur autorisée est épuisée.

Enregistrer :
- quantité demandée ;
- quantité exécutée ;
- quantité non exécutée ;
- prix moyen pondéré ;
- niveaux consommés ;
- valeur brute ;
- frais estimés ;
- snapshot de référence ;
- hypothèses de latence et de liquidité.

Ne pas supposer que toute la quantité est exécutée au meilleur bid/ask. Si la profondeur est insuffisante, autoriser un fill partiel ou un reliquat non exécuté.

## 5. Spread, slippage et référence de prix

Calculs de base :
- `spread_abs = best_ask - best_bid`
- `mid_price = (best_ask + best_bid) / 2`, si les deux côtés existent et sont valides.
- `spread_bps = spread_abs / mid_price * 10_000`, si `mid_price > 0`.

Le slippage doit être défini par rapport à une référence explicitement choisie, par exemple le mid-price au moment de la décision ou le meilleur prix exécutable observé. Ne pas mélanger les définitions dans un même rapport.

Le coût de profondeur est capturé par le prix moyen pondéré d'exécution. Le spread et le slippage peuvent se recouper selon la référence choisie ; documenter la convention afin d'éviter le double comptage.

## 6. Frais

- Ne pas coder un taux universel supposé valable pour tous les marchés.
- Utiliser les règles officielles applicables au marché et au moment de l'événement, après vérification dans la documentation officielle.
- Enregistrer la source, la date de vérification, la version du calculateur et les paramètres utilisés.
- Si le barème applicable est inconnu, marquer le résultat comme incomplet et ne pas prétendre fournir un PnL net définitif.
- Distinguer frais d'entrée et de sortie lorsque le modèle applicable le requiert.
- Les éventuelles remises, récompenses ou conditions spéciales ne doivent être intégrées que si elles sont vérifiables et pertinentes.

## 7. Capital et portefeuille virtuels

Tester des capitaux de référence dans la plage 100 à 10 000 USD/USDC. Scénarios initiaux suggérés :
- 100
- 250
- 500
- 1 000
- 2 500
- 5 000
- 10 000

Les scénarios doivent être configurables. Pour comparer les stratégies, conserver les mêmes hypothèses de capital et de risque dans les tests correspondants.

Le moteur doit empêcher :
- les achats dépassant le cash disponible ;
- la vente d'une quantité supérieure à la position détenue, sauf si un mécanisme de position courte est explicitement implémenté et autorisé par les règles du marché ;
- les positions dépassant les limites définies ;
- le double comptage d'un fill ;
- la création d'un cash fictif à partir du PnL latent.

Ne pas supposer qu'un « short » est disponible de la même manière que dans un marché à marge traditionnel. Modéliser les tokens/résultats et les transactions autorisées par le marché Polymarket concerné.

## 8. Valorisation et PnL

Conserver séparément :
- cash ;
- quantités détenues par token ;
- coût de revient ;
- frais payés/estimés ;
- PnL réalisé ;
- PnL latent ;
- valeur liquidative estimée ;
- exposition par marché et par événement.

La valorisation de sortie doit utiliser un prix réellement exécutable estimé du côté opposé du carnet, pour la taille de position considérée, lorsque la profondeur est disponible. Le mid-price peut être affiché à titre informatif mais ne doit pas être confondu avec une valeur de liquidation garantie.

Pour les marchés résolus, appliquer les règles de règlement documentées. Séparer le résultat de règlement du PnL latent pré-résolution.

## 9. Ordres et exécutions partielles

Chaque ordre virtuel possède un identifiant unique et un statut :
- proposé ;
- accepté par le simulateur ;
- exécuté partiellement ;
- exécuté ;
- expiré/abandonné ;
- rejeté (données périmées, liquidité insuffisante, limite de risque, etc.).

Chaque fill est une écriture immuable avec prix, quantité, frais, horodatages et référence au snapshot. Les mises à jour de portefeuille doivent être idempotentes.

## 10. Gestion des erreurs et garde-fous

Suspendre ou marquer la stratégie comme dégradée si :
- le flux est déconnecté ;
- les timestamps sont trop anciens ;
- le carnet est invalide ou un côté manque ;
- les données sont hors ordre sans traitement explicite ;
- le calculateur de frais n'a pas de barème vérifié ;
- le portefeuille ne se réconcilie pas ;
- une limite de risque est dépassée.

La suspension doit être visible dans le dashboard et le journal.

## 11. Extensions prévues

V2 — maker :
- file d'attente approximée ;
- priorité prix/temps ;
- probabilité de fill ;
- annulations et changements de carnet ;
- exécutions partielles ;
- adverse selection ;
- mesure de la qualité de la simulation.

V3 — améliorations possibles :
- modèle empirique de latence ;
- carnet historique si disponible ;
- simulation de plusieurs stratégies en concurrence pour la même liquidité ;
- stress tests automatiques et rapports de robustesse.
