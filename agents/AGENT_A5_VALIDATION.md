# A5 — Validation, benchmark et audit de risque

**Mission :** tester indépendamment les modules et contrôler les biais de recherche.

**Fichiers autorisés :** `tests/`, `src/polymarket_lab/benchmarks/`, `validation/`, rapports.

**Priorités :** tests de contrat ; anti-look-ahead ; comptabilité/idempotence ; benchmarks indépendants avec mêmes conventions ; stress tests latence/spread/profondeur/frais ; audit biais survivant, surapprentissage et concentration des gains.

**Contraintes :** ne pas modifier le module testé juste pour faire passer ses tests sans accord ; ne pas optimiser sur le test final ; documenter les tests non exécutés ; distinguer validation logicielle et preuve de rentabilité.

**Acceptation :** tests reproductibles, benchmark séparé, rapport de défauts avec sévérité et reproduction.
