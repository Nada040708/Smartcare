# Étape 3 — Capteur simulé et scénarios

## Objectif et classes

Produire les mesures structurées de l'étape 2 à chaque cycle, avec des scénarios
contrôlés et un état indépendant pour chaque patient.

| Classe UML | Implémentation | Rôle |
| --- | --- | --- |
| `SensorDevice` | `src/simulation/sensor_device.py` | Interface abstraite : appareil, patient, état, lecture |
| `SensorSimulator` | `src/simulation/sensor_simulator.py` | Appareil virtuel multiparamètre affecté à un patient |
| `GenerationStrategy` | `src/simulation/strategies/generation_strategy.py` | Production de la prochaine valeur ou absence |
| `NormalStrategy` | `normal_strategy.py` | Petites variations dans un intervalle explicite |
| `ProgressiveAnomalyStrategy` | Alias de `ProgressiveStrategy` | Variation cumulée par cycle |
| `SuddenAnomalyStrategy` | Alias de `SuddenChangeStrategy` | Un seul saut configurable |
| `MissingDataStrategy` | `missing_data_strategy.py` | Aucune observation pour le paramètre |
| `RecoveryStrategy` | `recovery_strategy.py` | Retour progressif vers une cible |

Les deux noms historiques restent utilisables. Les méthodes UML sont traduites
en `snake_case`, notamment `simulate_failure()` et `get_status()`.

## Configuration d'un simulateur

```python
from src.domain import Patient, HypertensionProfile
from src.domain.parameters import HeartRate, BloodPressure
from src.simulation import SensorSimulator
from src.simulation.strategies import NormalStrategy, ProgressiveAnomalyStrategy

patient = Patient("P001", "Patient 1", profiles=[HypertensionProfile()])
patient.add_parameter(HeartRate())
patient.add_parameter(BloodPressure())

simulator = SensorSimulator(
    patient=patient,
    device_id="SIM_P001",
    interval=1,
    strategies={
        "heart_rate": NormalStrategy(60, 100),
        "systolic_bp": ProgressiveAnomalyStrategy(step=2),
        "diastolic_bp": ProgressiveAnomalyStrategy(step=1),
    },
)
simulator.start()
try:
    for measurement in simulator.read():
        print(measurement.to_json())
finally:
    simulator.stop()
```

Un simulateur représente ici **un appareil virtuel multiparamètre pour un
patient**. Son identifiant par défaut est `SIM_<patient_id>`. Pour plusieurs
appareils d'un même patient, fournir des identifiants distincts.

Ajouter les paramètres au patient avant de construire le simulateur. Celui-ci
copie leurs états initiaux et les stratégies : les valeurs et compteurs ne sont
pas partagés entre patients, même si la configuration source réutilise des
objets. Modifier ensuite `patient.parameters` ne reconfigure pas le simulateur ;
construire un nouvel appareil pour changer sa liste de paramètres.

`set_strategy("heart_rate", nouvelle_stratégie)` remplace le scénario et remet
son compteur à zéro, en conservant la dernière valeur du paramètre.
`set_strategy("heart_rate", None)` rétablit la génération par défaut.

## Cycle de lecture et temps

`start()` active l'appareil mais ne crée ni thread ni boucle automatique.
`read()` et son alias `generate_measurements()` produisent un cycle sous forme
de `list[Measurement]`. Une liste vide signifie qu'aucune mesure n'est émise.

`interval` est un nombre positif et fini de secondes. L'appelant applique
l'attente ; `main.py` utilise `time.sleep(interval)`. L'exemple de scénarios
avance volontairement les cycles sans attendre. Les dates restent les dates
réelles de génération, pas une horloge virtuelle avancée d'une seconde.

Sans stratégie, chaque paramètre génère une nouvelle valeur dans son intervalle
de démonstration. Avec une stratégie, la première valeur courante est celle
préconfigurée via `record_value()`, ou une valeur initiale générée si nécessaire.
La stratégie calcule ensuite la première observation émise. Chaque lecture
émise possède un nouvel horodatage UTC et un nouvel identifiant de lecture.

`record_value()` valide et enregistre une sortie de stratégie. Une donnée
invalide provoque une erreur et restaure la lecture précédente. Ne pas affecter
manuellement `value`, car cela ne mettrait pas à jour l'horodatage.

## Scénarios

| Scénario | Configuration | Comportement |
| --- | --- | --- |
| Normal | `NormalStrategy(60, 100)` | Variation aléatoire entre −1 et +1, bornée à l'intervalle |
| Progressif | `ProgressiveAnomalyStrategy(step=5)` | 80 → 85 → 90 → 95 |
| Baisse progressive | `ProgressiveAnomalyStrategy(step=-5)` | 80 → 75 → 70 |
| Brutal différé | `SuddenAnomalyStrategy(change=65, trigger_after=2)` | Depuis 80 : 80, 80, 145, 145… |
| Données manquantes | `MissingDataStrategy()` | Aucun message pour le paramètre ; jamais une valeur zéro fabriquée |
| Retour à une cible | `RecoveryStrategy(target_value=80, step=25)` | Depuis 145 : 120, 95, 80, 80… |

Les intervalles et cibles sont des paramètres de démonstration, pas des règles
médicales. Les valeurs anormales restent disponibles pour l'analyse. Une
configuration qui viole la structure, comme un indice d'activité hors de [0, 1]
ou une tension diastolique supérieure à la systolique, produit une erreur
explicite ; elle n'est pas corrigée silencieusement.

## Pression artérielle et absence partielle

Les stratégies de tension sont configurées par `systolic_bp` et `diastolic_bp`,
jamais par `blood_pressure`. Les deux résultats sont exportés ensemble avec le
même patient, appareil, instant et `reading_id`, et deux `measurement_id`.

Lorsqu'une seule composante a une stratégie, l'autre conserve sa valeur courante.
Sans stratégie sur aucune composante, une nouvelle paire est générée à chaque
cycle. Si l'une des stratégies renvoie `None`, toute la paire est omise : aucune
ancienne composante n'est présentée comme une nouvelle lecture.

Un cycle invalide ne modifie ni les valeurs internes ni les compteurs des
stratégies. Les cycles omis ne font pas progresser le scénario du paramètre
concerné ; ils ne bloquent pas les autres paramètres.

## Arrêt, panne et reprise

| Situation | `status` | Résultat de `read()` |
| --- | --- | --- |
| Avant `start()` ou après `stop()` | `STOPPED` | `[]` |
| Appareil actif, patient activé | `RUNNING` | Mesures disponibles |
| Après `simulate_failure()` sur un appareil actif | `FAILED` | `[]` |
| Patient avec `monitoring_enabled=False` | `DISABLED` si actif et sans panne | `[]` |

L'ordre de priorité des états est arrêt, panne, désactivation, fonctionnement.
`restore()` retire la panne ; il ne démarre pas un appareil arrêté et ne
réactive pas la surveillance d'un patient. Un nouvel appel à `start()` ne
répare pas une panne. Les périodes sans émission ne modifient pas les valeurs.

Une `MissingDataStrategy` laisse l'appareil `RUNNING` : elle représente une
absence d'observation, pas une panne de tout l'appareil. Pour reprendre,
remplacer cette stratégie. Après une panne, `restore()` autorise de nouvelles
lectures mais ne signifie pas que les paramètres physiologiques sont redevenus
normaux. `RecoveryStrategy` sert séparément au retour progressif vers une cible.

La détection distante des timeouts, les événements `DISCONNECTED`/récupération,
les alertes techniques et leur résolution relèvent de `ConnectionMonitor` et
seront implémentés à leur étape. Les états décrits ici sont ceux du simulateur.

## Démonstrations et vérification

```sh
# Deux patients : normal, progressif, brutal, absence, panne et reprise.
.venv/bin/python -m examples.step3_simulation

# Prototype complet local, sans réseau : deux cycles, puis arrêt.
.venv/bin/python main.py --storage memory --no-mqtt --cycles 2 --interval 0.01

# Vérification locale (intégration MQTT ignorée par défaut depuis l'étape 4).
.venv/bin/python -m pytest -q
```

L'exemple fixe les valeurs initiales avec des stratégies aux bornes identiques.
P001 passe de 80 à 85, 90, 95 puis 145 bpm ; P002 reste à 75 bpm. Pendant la
panne de P001, P002 continue. La reprise de P001 donne 120, 95 puis 80 bpm.

Les tests vérifient les trajectoires, l'indépendance multipatient, les dates et
identifiants, la cohérence de la tension, les absences, l'arrêt, la désactivation,
la panne, la reprise et l'annulation d'un cycle invalide. Les deux anciens tests
qui appelaient `NormalStrategy()` sans bornes ont été mis à jour.

## Raccordement au prototype et suite

L'ancien appel `generate_measurement(patient, strategies)` retournant un lot est
remplacé par la configuration au constructeur puis `read()` ou
`generate_measurements()`. `Measurement(..., values={...})` reste disponible
pour la compatibilité de certaines parties du prototype.

`main.py` publie et stocke chaque mesure structurée séparément. Depuis
[l'étape 6](step6_rules.md), il fournit les mesures acceptées du cycle au moteur
de règles par profil, qui conserve une fenêtre temporelle par patient. L'ancien
lot temporaire pour le détecteur a été supprimé. Les graphes des nouveaux
paramètres restent à implémenter à l'étape dashboard.

Sans `--no-mqtt`, le programme utilise le publisher existant et attend un broker
local sur le port 1883. Le trajet MQTT → Mosquitto → Node-RED a depuis été
implémenté et vérifié dans [l'étape 4](step4_mqtt_nodered.md).
