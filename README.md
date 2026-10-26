# Polymarket Strategy Research Lab — kit de développement

Ce kit prépare la prochaine étape : verrouiller contrats et interfaces avant de lancer les agents en parallèle.

## Documents
- `CLAUDE.md` : règles globales et garde-fous.
- `COORDINATION.md` : responsabilités et ordre de lancement des six agents.
- `DECISIONS.md` : décisions validées et questions ouvertes.
- `ROADMAP.md` : phases de réalisation.
- `TASK_TEMPLATE.md`, `EXEMPLES_TACHES.md` : tâches reproductibles.
- `agents/` : prompts de mission par agent.
- `skills/` : pratiques réutilisables.
- `contracts/` : contrats JSON.
- `schemas/initial_db_schema.sql` : proposition de schéma SQLite.
- `configs/app.example.yaml` : configuration exemple.
- `tasks/TASK-001_ARCHITECTURE_REVIEW.md` : première tâche à lancer.

## Ordre recommandé
1. Extraire ce kit à la racine du dépôt de projet.
2. Copier les documents de cadrage précédents à la racine si ce n'est pas déjà fait.
3. Initialiser Git.
4. Ouvrir une session Claude Code dédiée à A0 et lui donner `tasks/TASK-001_ARCHITECTURE_REVIEW.md`.
5. Examiner les modifications et valider les contrats.
6. Seulement après cette validation, lancer A1, A2, A3, A4 et A5 sur des tâches séparées.

Les contrats et le SQL sont des propositions de départ, pas des interfaces définitivement validées. Les endpoints et règles Polymarket doivent être vérifiés dans la documentation officielle au moment de l'implémentation.
