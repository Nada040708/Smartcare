# Étape 4 — Python → MQTT → Mosquitto → Node-RED

## Objectif et résultat

Transmettre une mesure structurée depuis Python, la recevoir dans Mosquitto,
la décoder dans Node-RED et afficher son patient, son paramètre, sa valeur et
son unité. Le trajet est multipatient : P001 et P002 utilisent le même flow.

```text
SensorSimulator
    ↓ Measurement.to_json()
MQTTPublisher — QoS 1 → Mosquitto
                           ↓ health/+/vitals
                        MQTT IN
                           ↓
                        JSON
                           ↓
                   Contrôle de l'enveloppe
                      ↙             ↘
                 Debug          MQTT OUT
              + journaux   health/<patient_id>/received
                                      ↓
                             Test Python de réception
```

Le dernier message est un **reçu technique de démonstration**. Il prouve que
Node-RED a décodé le message et exécuté le flow ; ce n'est ni une alerte clinique
ni une confirmation de stockage.

## Fichiers et correspondance avec l'UML

| Élément | Fichier | Rôle |
| --- | --- | --- |
| `MQTTPublisher` | `src/communication/mqtt_publisher.py` | Connexion, publication et attente du broker |
| `MosquittoBroker` | `compose.yaml`, `infra/mosquitto/mosquitto.conf` | Service broker MQTT |
| `MQTTSubscriber` | Nœud `MQTT IN` de `infra/node-red/flows.json` | Abonnement aux patients |
| `NodeREDFlow` | `infra/node-red/flows.json` | Décodage, contrôle minimal, affichage et reçu |
| Configuration Node-RED | `infra/node-red/settings.js`, `start.sh` | Démarrage et conservation du flow |
| Démonstration et contrôle | `examples/step4_mqtt.py` | Vérification de quatre mesures de deux patients |

Mosquitto et Node-RED sont de vrais services. On ne les remplace pas par des
classes Python portant simplement leur nom. Le subscriber Python de l'exemple
observe uniquement les reçus ; le subscriber applicatif est le nœud Node-RED.

## Démarrage

Prérequis : environnement Python du projet, Docker Desktop démarré avec Docker
Compose. Les commandes suivantes sont exécutées depuis la racine de Smartcare.

```sh
.venv/bin/python -m pip install -r requirements.txt
docker compose up -d --wait
docker compose ps
```

Le téléchargement des images peut prendre plusieurs minutes au premier
lancement. La configuration utilise `eclipse-mosquitto:2.0` et
`nodered/node-red:4.1.15-22`. Le publisher Python utilise l'API Paho 2.x.

Ouvrir [Node-RED local](http://localhost:1880), sélectionner l'onglet
**Smartcare — Étapes 4 et 5**, puis ouvrir le panneau **Debug** à droite. Le flow est
chargé automatiquement ; aucun import ni bouton Deploy n'est nécessaire au
premier lancement. Le nœud MQTT doit afficher un état connecté.

Pour suivre également les messages dans le terminal :

```sh
docker compose logs -f node-red
```

## Démonstration de bout en bout

```sh
.venv/bin/python -m examples.step4_mqtt
```

Résultat attendu :

```text
Node-RED reçu : P001 | heart_rate = 84 bpm
Node-RED reçu : P001 | systolic_bp = 120 mmHg
Node-RED reçu : P001 | diastolic_bp = 80 mmHg
Node-RED reçu : P002 | heart_rate = 75 bpm
OK : 4 mesures, 2 patients, trajet Python → Mosquitto → Node-RED vérifié.
```

L'ordre d'affichage n'est pas contractuel. Le test génère des identifiants
nouveaux, s'abonne aux reçus et attend le SUBACK avant de publier. Il compare
ensuite tout le contenu retourné par Node-RED aux mesures envoyées : patient,
appareil, valeur, unité, date, identifiants et métadonnées. La pression artérielle
conserve son identifiant de lecture commun.

Pendant le démarrage de Node-RED, l'exemple peut republier les mêmes identifiants
jusqu'à la réception de tous les reçus. Les doublons ne sont comptés qu'une fois
**dans ce test** ; le flow ne réalise pas encore de déduplication applicative.

Le publisher attend le CONNACK à la connexion et le PUBACK après chaque
publication QoS 1. Cela confirme la réception par le broker, pas par Node-RED.
C'est le reçu technique supplémentaire qui vérifie la dernière partie du trajet.
En cas d'erreur ou d'expiration du délai, la commande termine avec un code non nul.

## Exécution du prototype

```sh
# Deux cycles avec publication des paramètres de P001.
.venv/bin/python main.py --cycles 2

# Exécution continue, Ctrl+C pour arrêter.
.venv/bin/python main.py

# Mode local sans MQTT, toujours disponible.
.venv/bin/python main.py --storage memory --no-mqtt --cycles 2
```

Le traitement Python (règles par profil depuis l'étape 6, stockage PostgreSQL
depuis l'étape 8 ou `--storage memory`, et affichage)
reste présent dans `main.py`. À cette étape, il s'exécute directement côté Python,
sans attendre une décision de Node-RED. Son remplacement par le chemin complet
Node-RED → backend → stockage interviendra aux étapes suivantes.

## Topics et format

| Topic | Producteur | Consommateur |
| --- | --- | --- |
| `health/P001/vitals` | Simulateur Python P001 | Node-RED |
| `health/P002/vitals` | Simulateur Python P002 | Node-RED |
| `health/+/vitals` | Filtre d'abonnement | Reçoit tous les patients |
| `health/<patient_id>/received` | Node-RED | Test de bout en bout |
| `smartcare/healthcheck` | Contrôle Docker du broker | Aucun traitement clinique |

Chaque publication contient une seule mesure JSON du format de l'étape 2.
Le topic par défaut du publisher est `health/{patient_id}/vitals`. Les
identifiants patients doivent utiliser des lettres ASCII, chiffres, `_` ou `-`
pour rester un seul segment MQTT. Les messages ne sont pas retenus (`retain=False`).

Le flow utilise QoS 1 et MQTT 3.1.1. QoS 1 autorise des doublons ; les
`measurement_id` serviront à la déduplication lors du stockage persistant.

## Contrôles déjà présents et limites

À l'étape 4, le flow contrôlait seulement l'enveloppe nécessaire à la démonstration :

- JSON décodable et objet structuré ;
- champs d'identification, paramètre, unité, qualité et date non vides ;
- valeur numérique finie et date portant un fuseau ;
- concordance entre `patient_id` et le topic ;
- rejet des messages retenus pour cette démonstration de données courantes.

Depuis [l'étape 5](step5_validation.md), le flow contrôle aussi les unités,
paramètres connus, bornes techniques configurées, fraîcheur, qualité et
métadonnées. Un rejet apparaît dans **Message rejeté** et produit un résultat
technique sur `health/<patient_id>/rejected`, sans message sur `/received`.
Les anciens lots `values={...}` ne sont pas acceptés. Les seuils par profil,
la détection des tendances, les alertes techniques de déconnexion et leur
résolution restent à implémenter aux étapes correspondantes.

Le broker autorise les connexions anonymes pour cette démonstration locale.
Les ports hôtes sont liés à `127.0.0.1` ; TLS, comptes MQTT, ACL et authentification
de l'éditeur Node-RED ne sont pas encore configurés. Utiliser les patients fictifs
des exemples. La sécurité prévue dans l'UML reste une étape distincte.

## Ports, persistance et arrêt

Depuis Python exécuté sur l'ordinateur : `localhost:1883`.
Depuis le conteneur Node-RED : `mosquitto:1883`, via le réseau Docker.

Pour utiliser d'autres ports hôtes :

```sh
MQTT_PORT=1884 NODE_RED_PORT=1881 docker compose up -d --wait
.venv/bin/python -m examples.step4_mqtt --port 1884
.venv/bin/python main.py --mqtt-host localhost --mqtt-port 1884 --cycles 2
```

L'éditeur devient alors accessible à `http://localhost:1881`. Le port interne du
broker reste 1883. Réutiliser les mêmes variables lors des prochains démarrages,
ou les placer dans un fichier `.env` local ignoré par Git.

Le volume `node_red_data` conserve les modifications faites dans l'éditeur.
`start.sh` copie le flow du dépôt dans `/data/smartcare-flows.json` uniquement si
ce fichier n'existe pas. Le nom distinct évite de charger le flow vide fourni
par l'image. Modifier le fichier du dépôt ne remplace donc pas automatiquement
un flow déjà édité : l'importer depuis le menu **Import** de Node-RED, après avoir
exporté les éventuelles modifications à conserver.

Mosquitto n'a pas de persistance à cette étape. Un redémarrage ne rejoue pas
l'historique des mesures. Le reçu technique ne remplace pas une base de données.

```sh
# Arrêter sans supprimer les services ni les données Node-RED.
docker compose stop

# Redémarrer et attendre que les services soient prêts.
docker compose up -d --wait

# Retirer les conteneurs et le réseau ; conserver le volume Node-RED.
docker compose down
```

## Tests et diagnostic

```sh
# Tests locaux ; l'intégration MQTT est ignorée par défaut.
.venv/bin/python -m pytest -q

# Tous les tests, y compris la vraie chaîne MQTT/Node-RED sur les ports par défaut.
.venv/bin/python -m pytest -q --mqtt-integration

# Tester uniquement la fonction et le câblage du flow, sans Docker (Node.js requis).
node --test infra/node-red/flow.test.cjs
```

Les tests unitaires vérifient les erreurs de connexion, les délais, les topics,
la sérialisation, le nettoyage de la boucle réseau et les messages rejetés par
le flow. Le test d'intégration utilise réellement les deux services Docker.

| Symptôme | Vérification |
| --- | --- |
| Docker daemon inaccessible | Démarrer Docker Desktop, puis `docker info` |
| Port déjà utilisé | Choisir d'autres ports hôtes comme ci-dessus |
| Connexion MQTT refusée | `docker compose ps`, puis journaux Mosquitto |
| Broker joignable mais aucun reçu | Vérifier l'onglet Smartcare, l'état MQTT et les journaux Node-RED |
| Ancien flow visible | Le volume conserve le flow édité ; importer le flow du dépôt si nécessaire |
| Message rejeté | Lire **Message rejeté** dans Debug et vérifier le topic et le JSON |

## Références techniques

- [Paho Python — client, callbacks et attente de publication](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html).
- [Node-RED — utilisation avec Docker et volume de données](https://nodered.org/docs/getting-started/docker).
- [Mosquitto — méthodes d'authentification et option allow_anonymous](https://www.mosquitto.org/documentation/authentication-methods/).
