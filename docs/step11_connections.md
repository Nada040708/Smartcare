# Étape 11 — Pannes, reconnexion et données manquantes

## Résultat

Le système surveille maintenant la réception des données **par appareil et par
paramètre**. Il détecte automatiquement un capteur silencieux, un paramètre
absent dans un flux encore actif et la reprise de données fraîches. Les incidents
techniques sont stockés dans PostgreSQL et visibles dans le dashboard.

Les alertes physiologiques restent séparées : une panne ne résout pas une
anomalie médicale et le retour de la liaison ne prouve pas un retour à la normale.

```text
Mesure validée et nouvelle → ConnectionMonitor → état de réception
                                 ↑                    ↓
                  vérification chaque seconde    incidents techniques
                                                      ↓
                         transaction PostgreSQL + moteur clinique
                                                      ↓
                                   dashboard et journal des états
```

## Comportements

| Situation | Réception du capteur | État patient / résultat |
| --- | --- | --- |
| Aucun message, pendant le délai de démarrage | `WAITING` | Surveillance |
| Tous les paramètres attendus sont récents | `CONNECTED` | Selon les règles et alertes cliniques |
| Le capteur ne fournit plus de données valides | `DISCONNECTED` | Déconnecté et incident technique actif |
| Certains paramètres arrivent, un autre manque | `DEGRADED` | Surveillance au minimum ; une alerte clinique reste visible |
| Première donnée fraîche après une panne | Reprise de la réception | Incident de silence résolu ; données complètes encore nécessaires |
| Tous les paramètres sont renouvelés | `CONNECTED` | Retour normal possible si les règles sont claires et les alertes résolues |
| Patient dont la surveillance est désactivée | `PAUSED` | Aucun nouvel incident de délai |
| Récepteur arrêté, historique seul ou état trop ancien | `UNKNOWN` dans l'API | État non actualisé, jamais une connexion affirmée |

`WAITING`, `CONNECTED`, `DEGRADED`, `PAUSED` et `UNKNOWN` sont des états de
réception de l'appareil, distincts de l'énumération clinique `MonitoringState`.
`RECOVERY` est un événement, pas un diagnostic ni un nouvel état clinique.

Une absence prolongée sur **un appareil attendu** suffit à placer son patient
en `DISCONNECTED`. Les autres patients continuent d'être évalués. Les alertes
cliniques actives restent consultables, y compris lorsqu'une panne a priorité
dans l'état affiché du patient. Une nouvelle anomalie sur des données reçues
peut toujours ouvrir une alerte ; la panne interdit surtout les confirmations
de récupération injustifiées.

## Configuration

Le fichier `config/connection-policy.json` décrit les appareils attendus :

```json
{
  "timeout_seconds": 15,
  "startup_grace_seconds": 15,
  "devices": [
    {
      "patient_id": "P001",
      "device_id": "SIM_P001",
      "parameters": ["heart_rate", "glucose"]
    }
  ]
}
```

Cet extrait réduit illustre le format. Le fichier livré attend les neuf valeurs
scalaires du simulateur pour chacun des trois patients : les deux composantes
de pression artérielle comptent séparément.

- `timeout_seconds` : ancienneté maximale d'une mesure avant de considérer son
  paramètre manquant ; silence global si aucune donnée du capteur n'est récente.
- `startup_grace_seconds` : délai avant d'ouvrir un incident pour un appareil
  jamais reçu ou des paramètres initialement absents.
- `devices` : identité patient/appareil et paramètres que cet appareil doit fournir.

Les délais sont en secondes, entre 1 et 3600. Choisir des délais supérieurs à
la cadence normale et à sa variabilité. **15 secondes est une valeur de
démonstration pour le simulateur rapide, pas une recommandation clinique.**
Le seuil se déclenche lorsque l'ancienneté atteint le délai, avec le décalage
du prochain passage du récepteur (environ une seconde, davantage si une
tentative réseau bloque jusqu'à son timeout de trois secondes).

Pour charger une autre politique :

```sh
.venv/bin/python -m src.web --db-schema smartcare_dashboard_demo --connection-policy config/connection-policy.json
```

Les appareils d'un patient explicitement configuré doivent respecter cette
liste : un identifiant d'appareil ou paramètre inattendu est rejeté par le
récepteur, sans conservation de la mesure dans la transaction. Pour préserver
les exemples utilisant des patients supplémentaires, un patient sans appareil
déclaré peut découvrir ses appareils à la première donnée valide ; seuls les
paramètres déjà observés y sont alors surveillés. Un appareil jamais déclaré
et jamais reçu ne peut pas être déclaré déconnecté : déclarer les appareils
pour une démonstration complète du démarrage sans données.

La politique est chargée au démarrage, sans rechargement à chaud. Pour changer
la topologie de la démonstration, préférer un nouveau schéma afin de garder un
historique interprétable. Les anciennes lignes et incidents d'un appareil retiré
ne sont pas automatiquement effacés ou déclarés résolus. Désactiver la
surveillance ne constitue pas non plus une récupération d'un incident existant.

## Données fraîches et récupération

Le suivi utilise **l'horodatage de capture** des mesures validées, et non leur
seule heure d'arrivée. La validation technique existante contrôle structure,
unités, identité, qualité, ancienneté et tolérance d'horloge.

La base déduplique les identifiants de message et de lecture avant d'alimenter
le suivi. Les doublons, valeurs anciennes reçues tardivement, timestamps qui
reculent et messages invalides ne renouvellent pas artificiellement le délai.
La validation doit réussir avant toute modification persistante de réception.

Une panne ouvre un épisode `DISCONNECTED`, une absence partielle ouvre un
épisode `MISSING_DATA`. Les vérifications répétées réutilisent cet épisode ;
elles ne créent pas une nouvelle alerte à chaque seconde. Un épisode est résolu
avec une date de résolution et un événement `RECOVERY` référençant son identifiant.

Le silence est résolu par une nouvelle mesure récente capturée **après**
l'ouverture de la panne. Pour retrouver une réception complète, chaque paramètre
attendu doit être récent et renouvelé après l'ouverture du dernier incident.
Une reprise partielle peut donc résoudre le silence tout en laissant un incident
de données manquantes. Si les paramètres d'un même cycle arrivent séparément au
moment d'ouvrir cet incident, un cycle complet supplémentaire peut être nécessaire.

Lorsqu'un incident s'ouvre, l'historique en mémoire du détecteur est vidé pour
ce patient : une tendance ne doit pas relier artificiellement les périodes
avant et après la coupure. L'historique stocké en base reste conservé. Les règles
de tendance doivent disposer à nouveau de leur fenêtre d'observation.

Une alerte physiologique n'est jamais résolue grâce à une absence de données.
Les confirmations de récupération sont suspendues lorsque la réception est
incomplète ou déconnectée. Les deux confirmations fraîches prévues à l'étape 7
restent nécessaires pour résoudre une alerte clinique ; un simple retour MQTT
ne les remplace pas.

## Persistance et redémarrage

La migration `003_connections.sql` ajoute `device_connections`. Chaque ligne
contient l'état d'un couple patient/appareil, son démarrage, ses dernières dates
par paramètre, les paramètres attendus, la barrière de récupération et ses
épisodes techniques en cours. Les événements restent dans `technical_events`.

Mesures, réception, événements, alertes et état du patient sont enregistrés
dans la même transaction de `PersistentMonitoring`. Si une écriture échoue,
la transaction **et** les objets en mémoire reviennent à leur état précédent.
Le verrou existant empêche deux moteurs d'écrire simultanément dans le même schéma.

Au redémarrage, les dernières dates et identifiants d'incident sont restaurés.
Le délai ne repart pas artificiellement de zéro pour un appareil connu. Une
panne commencée avant l'arrêt reste un même épisode. Une absence survenue pendant
l'arrêt est détectée lors de la prochaine évaluation, avec cette heure de détection.

## Panne réseau et indisponibilité de la base

Le récepteur poursuit les vérifications de délai même lorsque MQTT ne répond
pas. Les tentatives de reconnexion utilisent un délai croissant de 1, 2, 4, 8,
puis 10 secondes au maximum. Un succès remet ce délai MQTT à une seconde.
Le retour du broker déclenche un nouvel abonnement ; seules de nouvelles données
reçues permettent ensuite de rétablir les appareils.

Une erreur de stockage ferme la session et la connexion MQTT. Le récepteur
essaie d'ouvrir une nouvelle session PostgreSQL avec un délai plafonné à dix
secondes. Les incidents et alertes sont restaurés une fois la base revenue.
Durant l'indisponibilité, l'API renvoie une erreur de service, sans données
inventées. Les droits d'accès de l'étape 10 restent obligatoires.

La bannière « Réception indisponible » correspond à la liaison MQTT ou au
récepteur global. Les cartes « Réception des capteurs » donnent l'état par
appareil. Le tableau de bord continue d'afficher les déconnexions calculées
lors d'une panne MQTT si le moteur et PostgreSQL fonctionnent encore.
La dernière valeur d'un paramètre signalé manquant est grisée et marquée
« Ancienne », même si elle n'a pas encore atteint les 120 secondes de la
politique générale de validation.

## Démonstration avec Docker et TLS

Préparer l'étape 10, le premier compte et la confiance dans la CA locale selon
[sa documentation](step10_security.md). Les commandes normales restent :

```sh
docker compose -f compose.yaml -f compose.secure.yaml up -d --wait
.venv/bin/python -m src.web --db-schema smartcare_dashboard_demo
```

Ouvrir **https://127.0.0.1:8000**, se connecter, puis dans un autre terminal :

```sh
.venv/bin/python -m examples.step11_degraded
```

Ce scénario fini effectue successivement :

1. Données complètes pour tous les patients.
2. Silence de P001 au-delà du délai ; P002 et P003 continuent.
3. Retour des données complètes de P001.
4. Absence de glycémie chez P001, alors que ses autres paramètres continuent.
5. Retour de toutes les données et résolution des incidents techniques.

Avec les délais par défaut, la démonstration dure environ une minute.
Observer P001 dans « Réception des capteurs », « Journal des états » et les
cartes du patient. P002/P003 servent de témoins. Après l'arrêt final du
simulateur, de nouveaux incidents sont attendus si la surveillance reste active.
Ne pas lancer un deuxième simulateur pour le même appareil pendant ce scénario :
ses données masqueraient volontairement le silence ou le paramètre absent.

Options : `--patient`, `--parameter`, `--patients`, `--connection-policy`,
`--mqtt-config`, `--broker`, `--port`, `--interval`. La cadence doit être
inférieure à la moitié du timeout. Le fichier de politique doit correspondre
à celui chargé par le dashboard.

## Vérification

Avec le profil Docker sécurisé en fonctionnement :

```sh
.venv/bin/python -m pytest -q --postgres-integration --tls-integration
```

Les tests à horloge contrôlée couvrent démarrage sans données, silence,
manque partiel, reprise, isolation des patients, doublons, retards,
configuration invalide et patient suspendu. Les tests PostgreSQL vérifient
transactions, incidents uniques, redémarrage, préservation des alertes cliniques
et absence de retour normal prématuré. Une interruption de connexion est
injectée dans un client réel puis la reconnexion TLS à Mosquitto est vérifiée,
sans arrêter les services utilisés par les autres démonstrations. Un autre test
injecte une indisponibilité temporaire PostgreSQL et vérifie la reprise du récepteur.

Le test navigateur utilise de vrais messages TLS et Node-RED :

```sh
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/check_connections_browser.py
```

Il crée une base logique isolée et un serveur HTTPS temporaire sur 8443,
deux patients et des comptes fictifs. Il vérifie un patient en panne, un patient
témoin, la reprise, la glycémie manquante et l'affichage mobile. Le serveur,
les comptes et le schéma de test sont supprimés à la fin. Les captures sont
`/tmp/smartcare-disconnection.png` et `/tmp/smartcare-missing-data-mobile.png`.
Comme le test navigateur de l'étape 10, il emploie une exception pour la CA locale
uniquement dans son navigateur éphémère.

## Fichiers et UML

| Élément | Emplacement |
| --- | --- |
| `ConnectionMonitor` | `src/processing/connection_monitor.py` |
| Appareils et délais | `config/connection-policy.json` |
| Persistance atomique | `src/processing/persistent_monitoring.py`, migration 003 |
| Reconnexion et boucle des délais | `src/web/receiver.py` |
| Gardes de récupération clinique | `alert_engine.py`, `monitoring_state_manager.py` |
| Données d'affichage et cartes | `src/web/queries.py`, `src/web/static/` |
| Scénario | `examples/step11_degraded.py` |

Le champ `technical_alerts` de chaque patient dans `/api/overview` expose les
incidents actifs de réception ; `devices` fournit les états des appareils et
les paramètres manquants. Les totaux des alertes existants restent **cliniques**.
Les endpoints restent protégés par les sessions et rôles de l'étape 10.

## Limites et prochaine étape

Un silence ne permet pas de déterminer à lui seul si le capteur, Node-RED ou
le réseau est responsable. Le système signale une absence de données valides,
pas une panne matérielle prouvée. Il dépend également de l'horloge UTC du
serveur et de la tolérance d'horloge du validateur.

Les sessions MQTT restent non persistantes et Mosquitto ne conserve pas les
messages dans ce profil. La reconnexion automatique ne garantit donc pas la
récupération des mesures émises pendant une coupure : il n'y a pas encore de
file locale de retransmission ni de garantie de livraison de bout en bout.
La déduplication conserve son rôle pour les messages effectivement reçus.

Les temporisations sont globales dans ce premier profil, sans délai propre à
chaque paramètre, ni remontée LWT/heartbeat dédiée. Les incidents techniques
restent dans le dashboard et le journal, sans notification SMS/e-mail.

La validation finale figure dans [l'étape 12](step12_validation.md), qui ajoute
également le consentement et le chiffrement des données physiologiques au repos.
