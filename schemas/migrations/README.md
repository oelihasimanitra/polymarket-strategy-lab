# Migrations SQLite

`schemas/initial_db_schema.sql` est la base **0.3**. Les migrations sont
appliquées dans l'ordre croissant après la base. Une base neuve s'obtient donc
en appliquant le schéma initial **puis** `0004_consolidation.sql` ; aucun
fichier 0.4 consolidé n'est dupliqué.

**Références auditées :** schéma `0.4` et migration `0004`. **Candidats non
approuvés :** `0005_p0_foundations.sql` (0.4 → 0.5),
`0006_p0_ledger.sql` (0.5 → 0.6) et
`0007_contract_sql_alignment.sql` (0.6 → 0.7). Ces trois fichiers ne doivent
pas être appliqués à la base de travail avant une décision explicite du
propriétaire.

## Base neuve (0.3 → 0.4)

Depuis la racine du dépôt, avec l'environnement virtuel :

```powershell
.\.venv\Scripts\python.exe -c "import pathlib, sys; sys.path.insert(0, 'src'); from polymarket_lab.storage.connection import ConnectionConfig, open_connection; c = open_connection(ConnectionConfig(r'data\lab.db')); c.executescript(pathlib.Path('schemas/initial_db_schema.sql').read_text(encoding='utf-8')); c.close()"
.\.venv\Scripts\python.exe schemas\migrations\run_migration.py --database data\lab.db
```

Le résultat attendu est `PRAGMA user_version = 4` et une ligne
`(4, '0004_consolidation')` dans `schema_migrations`.

## 0004 — consolidation contrats 1.1.0

Procédure obligatoire sur une base existante :

1. Arrêter tous les écrivains.
2. Copier le fichier SQLite et vérifier la copie :
   `PRAGMA integrity_check; PRAGMA foreign_key_check;`.
3. Vérifier `PRAGMA user_version = 3` et `schema_migrations` vide avant 0.4.
4. Exécuter la migration avec le runner, sur la copie, avec un seul écrivain :

   ```powershell
   .\.venv\Scripts\python.exe schemas\migrations\run_migration.py --database <copie.db>
   ```

   Le runner sélectionne la migration suivante dans le registre
   `3→0004`, `4→0005`, `5→0006`, `6→0007`, refuse une base inexistante ou vide, vérifie
   `user_version`, le journal attendu et la version cible. Il crée une
   sauvegarde cohérente via `Connection.backup` avant toute écriture et
   restaure ce fichier si la migration ou les contrôles post-migration
   échouent. Il annule la transaction en cas d'erreur et
   **restaure `PRAGMA foreign_keys = ON` et `PRAGMA recursive_triggers = ON`
   sur sa connexion dans tous les cas**, y compris après un échec. Ces pragmas
   n'étant pas persistants, chaque nouvelle connexion applicative doit passer
   par `polymarket_lab.storage.connection.open_connection`. Ne pas exécuter le
   script SQL directement avec un client qui laisserait la connexion ouverte
   après une erreur.
5. Vérifier après migration :
   - `PRAGMA user_version = 4` ;
   - une ligne `(4, '0004_consolidation')` dans `schema_migrations`, avec un
     `applied_at` canonique à six décimales (`...ffffffZ`) ;
   - `PRAGMA integrity_check = ok` ;
   - `PRAGMA foreign_key_check` vide ;
   - le runner a restauré `PRAGMA foreign_keys = ON` et
     `PRAGMA recursive_triggers = ON` sur sa connexion avant fermeture ; toute
     **nouvelle** connexion doit passer par la fabrique, car ces pragmas sont
     per-connexion et non persistants ;
   - comptages des tables avant/après identiques.
6. En cas d'erreur : ne pas réutiliser la copie partiellement migrée ;
   restaurer la sauvegarde et examiner l'instruction fautive. Les contrôles
   `integrity_check`/`foreign_key_check` du runner s'exécutent après le
   `COMMIT` du script SQL : un échec à ce stade ne peut pas être annulé par
   `ROLLBACK` et impose la restauration de la sauvegarde.

Le script refuse (`CHECK` de pré-vérification) les données 0.3 devenues
incompatibles : formules `per_share`/`custom`, `fee_charge_unit='outcome_token'`,
`fee_status='not_required'`. Il n'invente aucune valeur de remplacement.
Les lignes legacy peuvent conserver `normalizer_version`, `trader_visibility`,
`source_class` ou `custom_formula_ref` à `NULL`/valeur historique ; les nouveaux
inserts sont contrôlés par trigger. En particulier, `custom_formula_ref` reste
présent uniquement pour la lecture des lignes 0.3 : toute nouvelle valeur est
refusée, car la formule `custom` est suspendue en V1.

Le script refuse aussi les nouvelles transactions `kind='fee'` avec
`ref_type='fill'` : D-034 impose une transaction unique par fill, frais inclus.
Les éventuelles lignes legacy de ce type restent lisibles mais ne sont pas
recréées.

Le script n'est **pas** approuvé pour application à la base de travail tant que
les points bloquants du rapport A0 ne sont pas revus. Aucun commit ni gel n'est
associé.

## 0005 — candidat P0 (0.4 → 0.5)

`0005_p0_foundations.sql` prépare B-01 (identité v2), B-02 (manifestes/hashes)
et B-05 (provenance des fixtures). Il ajoute `event_identity_version`, les
index v1/v2 et de repli raw, reconstruit `event_replacements` avec
`visible_from_received_timestamp`, crée `manifest_events`,
`manifest_replacements`, `manifest_seals`, ajoute
`data_manifests.hash_version`/`event_id_algorithm` et
`experiments.config_hash_version`/`experiment_config_json`.

Préflight : un remplacement legacy dont `created_at` précède l'un des deux
événements fait échouer la migration ; aucune date n'est inventée. Les lignes
legacy reçoivent `event-identity=v1` (si la version de schéma est connue),
`hash_version='legacy/v1'`, `event_id_algorithm='event-id/v1'` et
`config_hash_version='legacy/v1'`. Aucun manifeste legacy n'est scellé.

Le script est **candidat non approuvé** ; il n'est pas exécuté sur la base de
travail.

## 0006 — candidat P0 (0.5 → 0.6)

`0006_p0_ledger.sql` prépare B-06. Il reconstruit `ledger_transactions` avec
`UNIQUE(experiment_id, ref_type, ref_id, kind)` et
`UNIQUE(experiment_id, idempotency_key)`, puis `settlement_conversions` avec
`experiment_id NOT NULL`, FK et
`UNIQUE(experiment_id, resolution_event_id, source_asset, target_unit)`.

Préflight : `settlement_conversions.experiment_id` est dérivé uniquement de
`ledger_transactions` avec `ref_type='market_resolution'`,
`ref_id=resolution_event_id` et `kind='settlement'`. Un ajustement ou une autre
transaction de résolution ne suffit pas. Zéro ou plusieurs expériences
distinctes ⇒ abort, aucune valeur inventée. Les
vues, index et triggers append-only sont recréés. Les collisions
`INSERT OR REPLACE` sur le ledger et les conversions sont refusées par des
triggers `BEFORE INSERT`, indépendamment de `recursive_triggers`. Le script est
**candidat non approuvé**.

Le runner nomme les sauvegardes avec un suffixe incrémental si deux migrations
sont appliquées dans la même seconde ; une collision de nom ne bloque plus la
seconde migration.

## 0007 — alignement contrats/SQL (0.6 → 0.7)

`0007_contract_sql_alignment.sql` aligne SQLite sur le contrat `experiment`
`1.2.0` : `research`, `validation` et `final_test` exigent
`end_time IS NOT NULL` ; `paper_live` peut rester ouverte ; une fin existante
doit rester strictement postérieure à `start_time`. Il reconstruit aussi
`fee_schedules` et `experiments` avec un défaut `schema_version = '1.2.0'`.
Les lignes existantes conservent leur `schema_version` d'origine (par exemple
`1.1.0` pour une ligne historique) ; aucun remplacement global n'est effectué.

Préflight : le runner compte les lignes
`period_type <> 'paper_live' AND end_time IS NULL` et refuse la migration avec
le nombre de lignes incompatibles. Le script SQL contient la même barrière
(`CHECK` sur une table temporaire), utilisable hors runner. Les données ne sont
jamais complétées par une date inventée. Les vues, index, FK et triggers des
tables reconstruites et des tables dépendantes sont recréés. Le runner vérifie
les comptages, `integrity_check`, `foreign_key_check` et restaure la sauvegarde
en cas d'échec avant ou après le `COMMIT`.

Le script est **candidat non approuvé** ; il n'est pas exécuté sur la base de
travail. Les migrations `0005` et `0006` ne sont pas modifiées.

## Traçabilité des fichiers de migration

`SHA256SUMS` contient la baseline SHA-256 des migrations SQL présentes. Son
en-tête déclare explicitement :

- `format: sha256sum-v1` ;
- `scope: schemas/migrations/*.sql` ;
- `covered:` la liste exacte des quatre migrations couvertes.

`tests/integration/test_migration_manifest.py` recalcule les hashes, vérifie
que la liste `covered` et les fichiers `.sql` réels sont exactement les mêmes,
refuse les doublons et épingle l'empreinte du manifeste après revue. Toute
modification d'une migration ou du manifeste exige une mise à jour explicite
et une revue A0. Un fichier `0008` ajouté sans mise à jour fait échouer le test.

Le manifeste n'est pas un fichier `.sql` et n'est pas enregistré dans le
runner de migration : il n'est jamais appliqué comme une migration.

Cette baseline est auto-référentielle au sens où elle décrit des fichiers du
même dépôt. Elle prouve l'identité actuelle relative à la baseline, pas
l'authenticité ni l'historique. Un acteur qui modifie une migration, le
manifeste, le test et la constante épinglée peut produire un état cohérent.
La preuve d'historique exige un commit Git de référence conservé par le
propriétaire. Dans l'état observé, `0004` à `0007` et `SHA256SUMS` ne sont pas
suivis par Git ; la non-modification historique ne pourra être prouvée
formellement qu'après leur ajout et leur commit, avec un diff de référence.
