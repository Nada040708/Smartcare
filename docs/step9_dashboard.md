# Étape 9 — Dashboard multipatient

> Mise à jour après l'étape 10 : la connexion est obligatoire. Préparer les
> certificats, démarrer le profil Docker sécurisé et créer le premier compte
> selon [l'étape 10](step10_security.md). Les commandes HTTP ci-dessous ne
> décrivent que l'ancienne démonstration locale ; le lancement actuel utilise
> HTTPS et MQTT/TLS. Les fonctions de consultation décrites ici sont conservées.

## Objectif et résultat

Consulter dans une interface web les patients, leurs profils, les dernières
mesures, les courbes, les alertes et le journal des états. Les informations
proviennent du stockage PostgreSQL de l'étape 8. Une réception MQTT continue
raccorde maintenant les reçus Node-RED au moteur Python et à la base.

Le dashboard est en français, adapté aux écrans de bureau et mobiles. Il se
rafraîchit toutes les trois secondes. Il ne contient pas de mesures fictives
injectées uniquement pour l'affichage : un schéma vide affiche des états vides.
Le simulateur fourni produit explicitement les données de démonstration.

```text
examples.step9_live (mesures simulées)
                ↓ health/{patient_id}/vitals
           Mosquitto → Node-RED (validation)
                ↓ health/{patient_id}/received
           MonitoringReceiver (validation Python)
                ↓
           PersistentMonitoring
           règles → alertes → états → PostgreSQL
                                         ↓
                          API FastAPI, lecture seule
                                         ↓
                    Dashboard HTML / CSS / JavaScript
```

L'interface utilise du JavaScript natif et des graphiques SVG, servis par
FastAPI. Ce choix évite une compilation frontend et des dépendances chargées
depuis un CDN pour cette étape. Un frontend React pourra réutiliser la même
API si nécessaire ; React n'est pas requis pour lancer ce dashboard.

## Lancement

Depuis la racine du projet, installer les dépendances puis démarrer les services :

```sh
.venv/bin/python -m pip install -r requirements.txt
docker compose -f compose.yaml -f compose.secure.yaml up -d --wait
```

Dans un premier terminal, lancer le dashboard et son récepteur :

```sh
.venv/bin/python -m src.web
```

Ouvrir **https://127.0.0.1:8000**, se connecter et attendre « Réception active », puis
lancer dans un second terminal :

```sh
.venv/bin/python -m examples.step9_live --port 8883 --mqtt-config .secrets/simulator.json
```

Le scénario par défaut publie 60 cycles, espacés de deux secondes, pour trois
patients. Chaque patient émet neuf valeurs scalaires : les huit paramètres du
projet, avec deux composantes pour la pression artérielle.

Sur un cycle de scénario de 40 passages :

- passages 0 à 9 : valeurs normales de démonstration ;
- passages 10 à 27 : hausse de glycémie/pression pour P001 et pattern au repos
  pour P002 ; à partir du passage 20, SpO₂ baisse aussi chez P002 ;
- passages 28 à 39 : retour aux valeurs normales ; les règles de l'étape 7
  confirment les récupérations selon les observations reçues.

Ce scénario se répète si le nombre de cycles le permet. Les seuils restent
ceux du catalogue pédagogique ; le système n'établit aucun diagnostic.

### Options utiles

```sh
# Démonstration dans un schéma séparé des données de l'application.
.venv/bin/python -m src.web --db-schema smartcare_dashboard_demo

# Consultation des données existantes sans lancer de récepteur MQTT.
.venv/bin/python -m src.web --no-ingest

# Autre port HTTP et configuration explicite du broker.
.venv/bin/python -m src.web --port 8001 --broker localhost --mqtt-port 8883

# Scénario sans anomalies, ou durée personnalisée.
.venv/bin/python -m examples.step9_live --scenario normal --cycles 30 --interval 2
```

Le récepteur écrit dans le schéma indiqué par `--db-schema`. Le simulateur
publie uniquement sur MQTT ; il ne connaît pas le schéma PostgreSQL.
Les paramètres de base de données restent ceux de `.env` et de l'étape 8.

**Une seule session de surveillance peut écrire dans un schéma.** Ne pas lancer
`main.py` en mode PostgreSQL et le dashboard avec ingestion dans le même schéma
en même temps. Le verrou de l'étape 8 empêche deux moteurs concurrents.
Le simulateur `examples.step9_live` est adapté à cette utilisation : il publie
les mesures et laisse le dashboard les traiter. `--no-ingest` reste utilisable
pour consulter un schéma déjà alimenté par un autre programme.

Le serveur est lié à `127.0.0.1`, avec un seul processus. Arrêter le simulateur
et le serveur avec `Ctrl+C` ; les historiques restent dans PostgreSQL.

## Patients et profils

`config/patients.json` définit le registre utilisé à la fois par le récepteur
et par la démonstration :

| Patient | Nom de démonstration | Profils |
| --- | --- | --- |
| P001 | Patient 01 | Diabète et hypertension |
| P002 | Patient 02 | Trouble anxieux / suivi stress |
| P003 | Patient 03 | Hypertension |

Les noms sont fictifs. Le fichier accepte `patient_id`, `name`, `profiles` et
`monitoring_enabled`. Les identifiants dupliqués ou incompatibles avec les
topics MQTT, les profils inconnus et les valeurs de configuration ambiguës
sont refusés. Redémarrer le serveur après modification de ce fichier.

Pour utiliser un autre registre, transmettre le même chemin aux deux programmes :

```sh
.venv/bin/python -m src.web --patients config/patients.json
.venv/bin/python -m examples.step9_live --patients config/patients.json
```

Un patient présent dans les mesures ou alertes historiques mais absent du
registre reste consultable avec la mention « Profil non configuré ». Aucun
profil n'est inventé pour lui ; le récepteur refuse ses nouveaux messages tant
qu'il n'est pas configuré.

## Fonctionnement de l'interface

| Élément | Fonction |
| --- | --- |
| Navigation latérale | Accès à la vue de suivi, aux alertes et au journal |
| Recherche de patient | Recherche par nom, identifiant ou profil ; sélection indépendante des autres patients |
| Compteurs | Patients, alertes actives, patients en état critique et nombre total de mesures |
| Fiche patient | Identifiant, profils, état et date de dernière mesure |
| Dernières mesures | Valeurs, unités, appareil et heure ; priorité du profil signalée par un point violet |
| Courbe | Choix parmi les neuf valeurs scalaires, périodes 15 min / 1 h / 24 h |
| Détail des valeurs | Tableau accessible sous la courbe, avec date, valeur, appareil et qualité |
| Alertes | Filtre active/résolue/toutes, filtre de sévérité, pagination de dix épisodes |
| Journal | Les dix derniers événements du patient, dont les transitions d'état |
| Pause / Actualiser | Suspendre le rafraîchissement de l'écran ou demander une lecture immédiate |

La pause concerne uniquement **l'affichage** : le récepteur continue de traiter
et de stocker les messages. Les filtres, la sélection du patient et la période
sont conservés lors du rafraîchissement. La sélection du patient est également
représentée dans l'URL, par exemple `?patient=P002`.

Les dates sont stockées en UTC et affichées dans le fuseau `Africa/Casablanca`.
Les unités des mesures restent celles du modèle partagé. Les courbes séparent
les appareils et ne relient pas deux points espacés de plus de deux minutes.
Elles tracent les observations, sans interpolation statistique ni prédiction.
La courbe affiche au plus les 240 dernières mesures de la période ; la limite
est annoncée quand elle est atteinte. Les points offrent un détail au survol et
les valeurs restent disponibles dans le tableau.

Un état `NORMAL` signifie uniquement que les règles configurées ont pu être
évaluées sans déclenchement et sans alerte active. Une valeur affichée n'est pas
un diagnostic. La résolution des alertes reste automatique, même après la mise
en place des droits d'accès de l'étape 10.

## Fraîcheur, réception et erreurs

Les mesures plus anciennes que la fenêtre technique du validateur (120 secondes
par défaut) sont grisées et portent la mention « Ancienne ». Une valeur absente
est représentée par `—`, jamais par zéro.

L'état courant vient du moteur en fonctionnement. Si le récepteur n'est pas
actif, que son évaluation date de plus de cinq secondes ou que le dashboard est
en mode historique, un ancien état `NORMAL` n'est pas réutilisé. Les alertes
actives restent visibles, avec leur sévérité ; sinon le patient apparaît en
`SURVEILLANCE`. Les états enregistrés dans le journal sont présentés comme un
historique, pas comme une preuve de l'état actuel.

« Réception active » signifie que le récepteur est connecté au broker et abonné
aux reçus Node-RED. **Cette indication ne prouve pas que chaque capteur est
connecté ou que Node-RED reçoit effectivement de nouvelles mesures.** Les heures
des valeurs permettent de constater leur fraîcheur. Les timeouts automatiques
par appareil et les événements de reconnexion restent prévus à l'étape 11.

En cas d'erreur API, un bandeau signale que les données peuvent être anciennes.
Les valeurs précédentes ne sont plus présentées comme actualisées. Le
rafraîchissement automatique réessaie, et le bouton Actualiser reste disponible.
Les requêtes dépassant dix secondes sont interrompues. Changer de patient ou
de filtre annule la requête précédente pour éviter qu'une réponse tardive
affiche les données du mauvais patient.

## Récepteur permanent

`MonitoringReceiver` utilise une boucle MQTT dans un thread dédié. Ce thread
possède sa connexion PostgreSQL et l'unique moteur `PersistentMonitoring` du
schéma. Les lectures HTTP utilisent des connexions distinctes.

Le récepteur s'abonne à `health/+/received`, vérifie l'identité du patient dans
le topic et conserve la validation du JSON et des métadonnées originales. Les
messages retenus, trop volumineux, mal routés ou associés à un patient inconnu
sont rejetés. La validation Python complète la validation de Node-RED.

Pour QoS 1, le récepteur acquitte après traitement. Un rejet de validation est
écarté ; une erreur de base de données arrête le récepteur et signale son
indisponibilité. La déduplication persistante de l'étape 8 empêche de compter
deux fois une même mesure. Les règles sont aussi réévaluées périodiquement avec
un cycle vide pour détecter l'expiration de leur contexte.

La connexion MQTT est réessayée en cas d'échec réseau. Cette boucle reste un
prototype avec une session MQTT non persistante : elle ne garantit pas la
relecture des messages émis pendant son arrêt ou une panne. Il faut relancer
le serveur après une erreur fatale de stockage. La fiabilité complète du
transport relève des étapes suivantes.

## API et fichiers

Les routes de données sont en lecture seule et nécessitent une session depuis
l'étape 10. Les pages Swagger/OpenAPI publiques ont été désactivées.

| Route | Contenu et filtres |
| --- | --- |
| `GET /api/overview` | Patients, profils, dernières mesures, états, compteurs et état du récepteur |
| `GET /api/patients/{id}/history` | `parameter`, `minutes` (1 à 10080), `limit` (1 à 600) ; mesures récentes retournées dans l'ordre chronologique |
| `GET /api/alerts` | `patient_id`, `status`, `severity`, `limit` (1 à 100), `offset` ; historique décroissant et total |
| `GET /api/patients/{id}/events` | Derniers événements, `limit` (1 à 100) |

Les patients inconnus renvoient `404`, les filtres invalides `422`, les erreurs
PostgreSQL `503` avec un message générique. Les identifiants sont passés comme
paramètres SQL. Les réponses ne sont pas mises en cache. Les noms et messages
sont échappés dans l'interface pour éviter leur interprétation comme HTML.

| Fichier | Rôle |
| --- | --- |
| `src/web/__main__.py` | Lancement local et options |
| `src/web/app.py` | API, fichiers statiques et cycle de vie du récepteur |
| `src/web/queries.py` | Lectures SQL destinées au dashboard |
| `src/web/receiver.py` | Abonnement MQTT, moteur et état de réception |
| `src/web/patients.py` | Chargement du registre et libellés des paramètres |
| `src/web/static/` | Interface HTML, styles et interactions JavaScript |
| `examples/step9_live.py` | Scénario multipatient envoyé via MQTT |
| `scripts/check_dashboard_browser.py` | Vérification optionnelle dans Chromium |

Le `Dashboard` console existant reste disponible dans `main.py`. Cette interface
web réalise les fonctions `selectPatient`, `displayMeasurements`, `displayGraphs`,
`displayAlerts`, `displayClinicalProfile` et l'affichage de réception prévu par
l'UML. La supervision des connexions individuelles sera complétée à l'étape 11.

## Vérification

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q --mqtt-integration --postgres-integration
```

Les tests ajoutés vérifient le registre, les filtres, les erreurs API, les états
vides, la fraîcheur, la séparation des patients, les historiques, la pagination,
les messages rejetés et le trajet réel MQTT → Node-RED → PostgreSQL → HTTP.

Pour la vérification navigateur optionnelle :

```sh
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium

# Lancer le serveur avec un schéma neuf, puis ce scénario fini.
.venv/bin/python -m src.security bootstrap --db-schema smartcare_dashboard_test_visuel
.venv/bin/python -m src.web --db-schema smartcare_dashboard_test_visuel
# Dans un autre terminal :
.venv/bin/python -m examples.step9_live --cycles 28 --interval 0.5 --port 8883 --mqtt-config .secrets/simulator.json
.venv/bin/python scripts/check_dashboard_browser.py --local-test-ca
```

Ce contrôle attend les patients et données du scénario fourni. Il vérifie la
sélection, la recherche, les courbes, les périodes, les filtres, le journal,
la pause, une panne API simulée et l'absence de débordement horizontal sur mobile.
Les captures sont écrites dans `/tmp/smartcare-dashboard-desktop.png` et
`/tmp/smartcare-dashboard-mobile.png`. Un autre emplacement peut être passé
avec `--screenshots`, et un autre port local avec `--url`.

## Limites et prochaine étape

L'interface reste locale. Les comptes, rôles, droits d'accès et TLS ont été
ajoutés à [l'étape 10 — sécurité](step10_security.md). Les profils
sont configurés dans le fichier JSON, sans formulaire d'administration.
Le nombre de points des courbes est limité, sans agrégation statistique ;
la vue d'ensemble vise le petit nombre de patients du prototype.

Le récepteur et la simulation doivent être démarrés pour démontrer les mises
à jour en direct. Les données historiques restent disponibles après leur arrêt.
La surveillance des connexions par appareil est disponible à
[l'étape 11](step11_connections.md). Les notifications externes et les mesures
de performance finales restent à compléter selon le plan du projet.

Références techniques : [cycle de vie FastAPI](https://fastapi.tiangolo.com/advanced/events/),
[tests avec lifespan](https://fastapi.tiangolo.com/advanced/testing-events/),
[client MQTT Paho et acquittement manuel](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html).
