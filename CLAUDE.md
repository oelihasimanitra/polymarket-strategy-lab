# Instructions globales — Polymarket Strategy Research Lab

## Objectif
Laboratoire local Windows pour étudier la reproductibilité de stratégies observées chez trois traders Polymarket sur les marchés crypto. V1 en paper trading uniquement.

## Contraintes absolues
- Aucun ordre réel, aucune clé d'ordre réel, aucun transfert de fonds.
- V1 : ordres taker simulés uniquement ; maker hors périmètre.
- Le code déterministe calcule exécutions, frais, portefeuille, PnL et métriques. Un LLM ne calcule pas le grand livre.
- Pas de look-ahead : une décision n'utilise que les données disponibles à son horodatage.
- Les frais doivent être vérifiés depuis une source officielle, datés et configurables ; aucun taux universel inventé.
- Données manquantes, carnet périmé et latence doivent être visibles.
- Ne jamais committer secrets, tokens, clés ou données privées.
- Ne pas prétendre qu'un test a réussi s'il n'a pas été exécuté.

## Travail
1. Lire les documents de cadrage et les contrats concernés.
2. Respecter le périmètre et les fichiers attribués à l'agent.
3. Toute modification d'interface partagée exige une proposition, une revue de l'architecte et des tests.
4. Ajouter/adapter les tests pour chaque comportement modifié.
5. À la fin, rapporter fichiers modifiés, tests exécutés et résultats, hypothèses, risques, blocages et prochaine étape.

## Définition de terminé
Livrable dans le périmètre, tests documentés, limites connues explicites, aucun secret ajouté.
