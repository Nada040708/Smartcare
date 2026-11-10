# Comprendre Smartcare en six étapes

Nous suivons **P001**, un patient fictif avec les profils diabète et hypertension.
Le professionnel observe ses mesures et les alertes. L’administrateur gère les accès
et enregistre les consentements. Tout le trajet ci-dessous fonctionne avec des données simulées.

## 1. Patients et profils

**À quoi ça sert ?** Identifier la personne et choisir les règles pertinentes. Un patient
peut cumuler plusieurs profils ; les règles communes continuent aussi de s’appliquer.

**Quel fichier regarder ?** [`config/patients.json`](../config/patients.json),
[`src/domain/clinical_profile.py`](../src/domain/clinical_profile.py).

**Comment le voir fonctionner ?** Dans Surveillance, sélectionner P001 puis P002 : leurs profils
et les mesures présentées en priorité diffèrent.

**Exemple :** la glycémie est prioritaire pour P001 diabétique. P002 est suivi pour un ensemble
fréquence cardiaque / HRV / respiration / activité, sans diagnostic d’anxiété.

## 2. Capteurs simulés

**À quoi ça sert ?** Produire des observations sans matériel médical. Une mesure possède
un patient, un appareil, un paramètre, une valeur, une unité, une date et une qualité.
Huit paramètres sont représentés par neuf valeurs scalaires, car la pression a deux composantes.

**Quel fichier regarder ?** [`src/demo.py`](../src/demo.py), fonction `scenario_readings`,
et [`examples/step9_live.py`](../examples/step9_live.py), fonction `cycle_measurements`.
Les stratégies plus détaillées restent dans `src/simulation/`.

**Comment le voir fonctionner ?** Serveur démarré, exécuter `python smartcare.py simulate normal`
dans le second terminal. Les valeurs et les heures se mettent à jour.

**Exemple :** `SIM_P001` émet une glycémie en `mg/dL`. Le scénario `anomaly` la porte à 240 ;
c’est encore une entrée du simulateur, jamais une valeur fabriquée dans le dashboard.

## 3. MQTT et Node-RED

**À quoi ça sert ?** Transporter les observations et organiser leur réception.
**MQTT est le protocole** de publication/abonnement. **Mosquitto est le broker** : il reçoit
les publications et les distribue aux abonnés. **Node-RED est l’orchestrateur** : son flow
reçoit et valide le message, puis le transmet au backend.

**Quel fichier regarder ?** [`src/communication/mqtt_publisher.py`](../src/communication/mqtt_publisher.py),
[`infra/node-red/flows.json`](../infra/node-red/flows.json),
[`infra/node-red/validator.cjs`](../infra/node-red/validator.cjs).

**Comment le voir fonctionner ?** Démarrer avec `python smartcare.py start-demo --node-red`,
puis ouvrir l’éditeur local HTTPS sur le port 1880, avec son compte en lecture seule.

**Exemple :** `health/P001/vitals` transporte la publication ; une mesure acceptée ressort
sur `health/P001/received`. Une mesure rejetée est dirigée vers `health/P001/rejected`.
**Node-RED valide les messages ; Python détecte les anomalies physiologiques.**

## 4. Validation, règles et alertes

**À quoi ça sert ?** Distinguer une donnée mal formée d’une mesure recevable qui déclenche
une règle. Les contrôles techniques portent notamment sur les unités, dates et bornes.
Les règles utilisent un seuil, plusieurs paramètres combinés ou une tendance temporelle.

**Quel fichier regarder ?** [`config/validation-policy.json`](../config/validation-policy.json),
[`config/monitoring-rules.json`](../config/monitoring-rules.json),
[`src/processing/anomaly_detector.py`](../src/processing/anomaly_detector.py),
[`src/processing/alert_engine.py`](../src/processing/alert_engine.py).

**Comment le voir fonctionner ?** Exécuter `python smartcare.py simulate anomaly`, sélectionner P001,
puis ouvrir Alertes. L’alerte provient du moteur Python après transmission réelle.

**Exemple :** 240 mg/dL est admis comme mesure technique mais déclenche la règle de glycémie haute
livrée pour le diabète. Des observations répétées actualisent un épisode ; des observations normales
renouvelées permettent sa résolution. Les seuils restent des paramètres pédagogiques modifiables.

## 5. PostgreSQL, API et dashboard

**À quoi ça sert ?** Conserver les mesures et rendre les résultats consultables. PostgreSQL
stocke les historiques ; FastAPI fournit les données aux pages HTML/CSS/JavaScript.
La déduplication évite d’enregistrer deux fois la même observation reçue plusieurs fois.

**Quel fichier regarder ?** [`src/processing/persistent_monitoring.py`](../src/processing/persistent_monitoring.py),
[`src/repositories/postgres_repositories.py`](../src/repositories/postgres_repositories.py),
[`src/web/app.py`](../src/web/app.py), [`src/web/static/app.js`](../src/web/static/app.js).

**Comment le voir fonctionner ?** Sélectionner P001, choisir « Glycémie » sur la courbe, puis changer
la période. Les mesures secondaires sont dans « Autres mesures ». Alertes est une vue séparée.

**Exemple :** la mesure de P001 est enregistrée, puis l’API `/api/patients/P001/history` fournit
son historique au graphique après vérification de la session et du consentement.

## 6. Sécurité et pannes

**À quoi ça sert ?** Contrôler les accès et signaler quand le suivi n’est plus fiable. Les mots
de passe sont hachés, les sessions et rôles sont vérifiés côté serveur, MQTT utilise TLS et le
site HTTPS. Le consentement contrôle la collecte ; les charges de mesures et d’alertes sont chiffrées.

**Quel fichier regarder ?** [`src/security/authentication.py`](../src/security/authentication.py),
[`src/security/demo.py`](../src/security/demo.py),
[`src/processing/connection_monitor.py`](../src/processing/connection_monitor.py),
[`config/connection-policy.json`](../config/connection-policy.json).

**Comment le voir fonctionner ?** Exécuter `python smartcare.py simulate disconnection`.
Observer P001 puis P002 : seul P001 se tait pendant la phase de coupure, avant de reprendre.

**Exemple :** après 15 secondes sans donnée valide avec la configuration livrée, P001 passe à
« Capteur déconnecté ». Le retour des données résout l’incident technique ; il ne prouve pas à lui
seul que les alertes physiologiques sont résolues. « À surveiller » signifie notamment que les
informations sont insuffisantes ou anciennes, pas qu’une maladie a été diagnostiquée.

Les données émises pendant une coupure ne sont pas garanties récupérables. La correspondance
IEEE 11073 est partielle. Les limites et la protection des clés sont décrites dans
[la documentation avancée](SECURITE_ET_TESTS.md).
