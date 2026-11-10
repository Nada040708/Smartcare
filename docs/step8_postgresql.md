# Étape 8 — Stockage persistant avec PostgreSQL

## Objectif

Conserver les mesures, les épisodes d'alerte et les événements techniques après
la fermeture du programme ou le redémarrage du conteneur PostgreSQL. Cette étape
reprend les trois dépôts de l'UML : `MeasurementRepository`, `AlertRepository`
et `EventRepository`.

**PostgreSQL avec Docker a été choisi pour le projet.** Le stockage est désormais
le comportement par défaut de `main.py`. Les exemples antérieurs peuvent encore
fonctionner en mémoire et `--storage memory` conserve ce mode pour le programme
principal.

```text
Mesures scalaires validées + patient/profils
                 ↓
PersistentMonitoring
  ├─ déduplication persistante
  ├─ règles → épisodes d'alerte → état du patient
  └─ transaction : mesures + alertes + changements d'état
                 ↓
PostgreSQL → volume Docker postgres_data
                 ↓
Consultation des historiques / reprise des alertes actives
```

Dans `main.py`, les mesures du simulateur sont analysées localement et peuvent
être publiées sur MQTT. Le mode `--mqtt` de l'exemple de cette étape vérifie
également l'entrée **Mosquitto → Node-RED → validation Python → PostgreSQL**.
Le [consommateur permanent et l'API du dashboard sont disponibles à l'étape 9](step9_dashboard.md).

## Démarrage

Depuis la racine du projet, avec Docker Desktop démarré :

```sh
.venv/bin/python -m pip install -r requirements.txt
docker compose up -d --wait
.venv/bin/python -m examples.step8_storage

# Même exemple, avec les deux premières mesures reçues de Node-RED.
.venv/bin/python -m examples.step8_storage --mqtt

# Programme principal : PostgreSQL, sans publication MQTT.
.venv/bin/python main.py --no-mqtt --cycles 2

# Programme principal : PostgreSQL et publication MQTT.
.venv/bin/python main.py --cycles 2

# Démonstration entièrement en mémoire, sans services Docker.
.venv/bin/python main.py --storage memory --no-mqtt --cycles 2
```

Le service PostgreSQL écoute sur **`127.0.0.1:5433`**, avec son port interne
`5432`. Le port hôte 5432 était déjà occupé sur la machine de développement ;
aucun changement n'a été apporté au service qui l'utilise.

| Configuration locale | Valeur par défaut |
| --- | --- |
| Hôte | `127.0.0.1` |
| Port hôte | `5433` |
| Base | `smartcare` |
| Utilisateur | `smartcare` |
| Mot de passe local | Défini uniquement dans `.env` via `POSTGRES_PASSWORD` |
| Schéma de l'application | `smartcare` |
| Image Docker | `postgres:17` |

Ces identifiants sont destinés au prototype local. Pour les personnaliser,
copier `.env.example` vers `.env` **si ce fichier n'existe pas déjà**, puis
adapter les variables `POSTGRES_*`. Compose et Python utilisent les mêmes
valeurs ; `.env` est exclu de Git. Les variables de l'environnement ont priorité.
`DATABASE_URL`, si définie, remplace les paramètres de connexion du client Python
uniquement. Elle ne reconfigure pas le conteneur Docker.

Les variables d'initialisation Docker définissent les comptes lors de la
création d'un volume neuf ; modifier `.env` ne modifie pas automatiquement le
mot de passe d'une base déjà initialisée. L'authentification applicative et le
durcissement des transports restent prévus à l'étape sécurité.

## Fichiers et classes

| Composant | Fichier | Responsabilité |
| --- | --- | --- |
| Service et volume PostgreSQL | `compose.yaml` | Base locale, port et contrôle de disponibilité |
| `PostgresStore` | `src/repositories/postgres_store.py` | Connexion, transactions, version du schéma et verrou de session |
| Migration initiale | `infra/postgres/migrations/001_initial.sql` | Tables, contraintes et index |
| Trois dépôts PostgreSQL | `src/repositories/postgres_repositories.py` | Sauvegarde et lecture des objets |
| Conversion des objets | `src/repositories/storage_codecs.py` | JSON explicite et dates UTC |
| `TechnicalEvent` | `src/domain/technical_event.py` | Événement technique conforme au rôle prévu par l'UML |
| `EventRepository` | `src/repositories/event_repository.py` | Version en mémoire |
| `PersistentMonitoring` | `src/processing/persistent_monitoring.py` | Cycle transactionnel et reprise du moteur |
| Démonstration | `examples/step8_storage.py` | Écriture, reprise et inspection |

Les dépôts PostgreSQL sont des implémentations distinctes qui offrent les
méthodes déjà utilisées : `save()`, `getByPatient()`, `getHistory()` et
`getActive()` pour les alertes. Les dépôts en mémoire restent disponibles pour
les anciens exemples. Les lectures PostgreSQL retournent des objets détachés :
modifier un objet Python ne modifie la base qu'après un nouvel appel à `save()`.

## Schéma SQL

| Table | Contenu et intégrité |
| --- | --- |
| `measurements` | Identifiant, patient, appareil, lecture, paramètre, valeur, unité, qualité, date et message JSONB ; une ligne par lecture scalaire |
| `measurement_receipts` | Identifiants des messages reçus, reliés à leur mesure canonique par clé étrangère ; conserve aussi les alias de lecture |
| `alerts` | Épisode et état courant, sévérité, dates, compteur et JSONB avec provenance/confirmation/résolution |
| `technical_events` | Événements techniques et transitions de surveillance, avec patient/appareil éventuels et détails JSONB |
| `schema_migrations` | Version du schéma installée |

Les colonnes structurées permettent les recherches et contraintes ; le JSONB
conserve les détails de l'objet. Les mesures incluent leurs métadonnées IEEE
11073 partielles de l'étape 2. `get_payload()` permet de relire leur message
stocké, avec dates normalisées en UTC. Les dates SQL sont des `TIMESTAMPTZ`.

Les index couvrent les recherches par patient/date et patient/paramètre/date.
Les identifiants sont uniques. Un index unique partiel impose **au plus un épisode
`ACTIVE` par `(patient_id, rule_id)`**. Les états, sévérités et certaines relations
entre dates sont également contraints en base.

Le schéma version 1 est créé automatiquement au premier accès, dans une
transaction protégée contre les initialisations concurrentes. Le rouvrir ne
réinitialise pas les données. Une version inconnue est refusée. Les évolutions
futures devront ajouter une migration et sa prise en charge ; il ne faut pas
réécrire la migration initiale d'une base déjà utilisée.

Les patients et leurs profils restent configurés dans le code : cette étape
n'ajoute pas de table de comptes ni d'administration des profils. Les références
de patients et les listes d'identifiants de preuves des alertes ne constituent
pas encore des clés étrangères vers un registre complet de patients.

## Doublons et mises à jour

Une mesure existante n'est jamais écrasée. Rejouer le même identifiant avec le
même contenu ne crée aucune ligne et ne réévalue pas les règles. Réutiliser
l'identifiant avec un autre contenu est rejeté.

La lecture est aussi identifiée par `(patient_id, device_id, parameter, reading_id)`.
La même lecture envoyée avec un nouvel identifiant de message est reconnue ;
l'alias est enregistré dans `measurement_receipts`. Réutiliser ensuite cet alias
avec un contenu différent reste détectable, même après redémarrage.

Pour les alertes, `save()` actualise l'épisode identifié par `alert_id`.
L'identité patient/règle/date d'ouverture ne peut pas être changée. Le compteur
d'occurrences et la dernière date ne peuvent pas reculer. Une alerte résolue
est conservée et ne peut pas être rouverte par un ancien objet `ACTIVE` : la
récidive crée un nouvel épisode, comme à l'étape 7.

Les événements `ACTIVE` peuvent être résolus ; les événements achevés
`RECORDED` ou `RESOLVED` sont immuables, hormis la réécriture identique.
Les événements produits à cette étape sont `MONITORING_STARTED` et
`STATE_CHANGED`. La détection automatique des timeouts reste prévue à l'étape 11.

## Transactions et reprise

`PersistentMonitoring.process()` possède sa transaction. Pour un cycle donné,
les nouvelles mesures, les modifications d'alertes et les changements d'état
sont validés ensemble. En cas de rejet ou d'erreur de sauvegarde, les écritures
SQL et les changements du détecteur, du moteur et du gestionnaire d'états sont
annulés. Le cycle peut alors être retenté sans être considéré comme déjà traité.
Ne pas envelopper cette méthode dans une transaction supplémentaire.

La validation des nouvelles mesures est effectuée avant le commit, y compris
pour un patient dont la surveillance est désactivée. Les lectures historiques
des dépôts ne repassent pas par le contrôle de fraîcheur : une mesure ancienne
reste consultable. Un message brut entrant passe par `process_payload()`, qui
valide aussi les métadonnées originales avant reconstruction.

Au démarrage d'une nouvelle session :

1. Les alertes actives sont chargées avec leurs identifiants, dates et occurrences.
2. Leurs confirmations de récupération sont remises à zéro et cette remise à
   zéro est sauvegardée.
3. Une récupération exige des observations capturées **après le redémarrage**.
4. Les anciens messages stockés restent des doublons, sans nouveau déclenchement.
5. Un événement `MONITORING_STARTED` indique combien d'alertes ont été restaurées.

L'historique récent utilisé pour les combinaisons et tendances n'est pas rejoué
dans le détecteur ; il se reconstitue avec les nouvelles observations. Les
alertes actives déterminent l'état initial restauré. Sans alerte, l'état revient
à `SURVEILLANCE` jusqu'à ce que les règles puissent être évaluées. Un ancien état
`NORMAL` enregistré dans les événements n'est pas une preuve de normalité actuelle.

Un verrou PostgreSQL autorise **une seule session de surveillance par schéma**,
avec plusieurs patients traités séquentiellement. Une seconde session est refusée
pour éviter que deux moteurs maintiennent des états divergents. Les connexions
de consultation restent possibles. Fermer la connexion libère le verrou.

Il n'y a pas de bascule silencieuse vers la mémoire si PostgreSQL est indisponible.
Le programme signale l'échec ; le mode mémoire doit être demandé explicitement.

## Démonstration en deux processus

Choisir un nom de schéma neuf à la première commande. Les données sont conservées
pour inspection ; la démonstration refuse d'écraser un schéma déjà rempli.

```sh
.venv/bin/python -m examples.step8_storage --phase seed --schema smartcare_demo_mon_essai --mqtt

# Facultatif : vérifier aussi la persistance du volume Docker.
docker compose restart postgres
docker compose up -d --wait postgres

.venv/bin/python -m examples.step8_storage --phase resume --schema smartcare_demo_mon_essai
.venv/bin/python -m examples.step8_storage --phase inspect --schema smartcare_demo_mon_essai
```

| Phase | Résultat attendu |
| --- | --- |
| `seed` | 3 mesures, deux patients, 1 alerte active avec une première confirmation |
| Fermeture du programme | Connexion fermée, données conservées |
| `resume` | Même alerte restaurée, confirmations à zéro, ancien message ignoré, anomalie persistante actualisée puis résolue après deux confirmations nouvelles |
| `inspect` | 6 mesures, 1 épisode résolu, 0 alerte active et journal des événements |

Sans `--phase`, l'exemple enchaîne ces opérations en fermant et rouvrant les
connexions. Sans `--schema`, il crée un nom `smartcare_demo_...` unique et l'affiche.
Les profils de cette démonstration sont les profils diabète, sans règles communes,
pour isoler le scénario de persistance. Le mode MQTT concerne les deux premières
mesures ; les observations de reprise sont produites localement.

## Consulter les données

```python
from src.repositories.postgres_store import PostgresStore
from src.repositories.postgres_repositories import PostgresMeasurementRepository, PostgresAlertRepository

with PostgresStore() as store:
    measurements = PostgresMeasurementRepository(store)
    alerts = PostgresAlertRepository(store)
    print(measurements.count('P001'))
    print(measurements.getByPatient('P001', limit=20, offset=0))
    print(alerts.getActive('P001'))
```

Les résultats sont triés par date puis identifiant. `limit` et `offset` permettent
de paginer ; sans limite, tout l'historique demandé est retourné. Le dashboard
console utilise `count()` pour ses compteurs, sans charger toutes les mesures.
Pour inspecter le schéma de l'application avec les valeurs par défaut :

```sh
docker compose exec postgres psql -U smartcare -d smartcare -c 'SELECT patient_id, count(*) FROM smartcare.measurements GROUP BY patient_id;'
docker compose exec postgres psql -U smartcare -d smartcare -c 'SELECT patient_id, rule_id, status, occurrences FROM smartcare.alerts ORDER BY timestamp;'
```

Les démonstrations utilisent leurs propres schémas : remplacer `smartcare` dans
ces requêtes par le nom affiché pour les consulter. Le schéma `smartcare` est
créé au premier lancement du programme principal ou à son ouverture via Python.

## Tests, conservation et limites

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q --postgres-integration
.venv/bin/python -m pytest -q --mqtt-integration --postgres-integration
```

Les tests PostgreSQL utilisent de vrais schémas `smartcare_test_...` isolés et
supprimés après chaque test. Ils vérifient notamment la réouverture, les alias
de messages, la pagination, les paramètres SQL, les contraintes d'alertes, les
résolutions, les transactions, les erreurs injectées, la reprise du moteur et
le trajet Node-RED vers PostgreSQL. Ils ne suppriment pas les données de l'application.

`docker compose stop` et `docker compose restart postgres` conservent le volume.
**`docker compose down -v` supprime les volumes et leurs données** : ne pas
l'utiliser pour simplement arrêter le projet. Le volume persistant n'est pas
une sauvegarde ; une procédure de sauvegarde/restauration reste à ajouter.

Cette étape ne fournit pas encore de pool de connexions, de partitionnement,
de rétention automatique, de moteur distribué, de reprise exacte des fenêtres
de règles, de chiffrement applicatif ni d'administration des profils. Le trajet
MQTT et la transaction SQL ne forment pas une transaction distribuée. La prochaine
étape est le [dashboard](step9_dashboard.md), maintenant disponible avec un
accès aux historiques persistants.

Références techniques : [image officielle PostgreSQL](https://hub.docker.com/_/postgres),
[transactions Psycopg 3](https://www.psycopg.org/psycopg3/docs/basic/transactions.html),
[INSERT et gestion des conflits PostgreSQL](https://www.postgresql.org/docs/17/sql-insert.html).
# Mise à niveau de confidentialité

Depuis l'étape 12, le stockage PostgreSQL exige une clé privée. Sur une
installation des étapes 8–11, exécuter `python -m src.security storage-key`,
arrêter l'ancien serveur puis relancer l'application pour la migration 4.
Voir [la migration et la sauvegarde de la clé](step12_validation.md).
