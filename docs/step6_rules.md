# Étape 6 — Moteur de règles selon les profils

## Objectif et périmètre

Appliquer aux mesures validées les règles associées aux profils du patient,
ainsi que les règles communes du prototype. La même glycémie peut déclencher
une règle chez P001, suivi pour diabète, sans déclencher cette règle chez P002,
suivi pour anxiété/stress. P001 peut aussi cumuler les règles d'hypertension.

Les règles de cette étape constituent un **catalogue de démonstration
configurable**, pas un protocole clinique validé ni un système de diagnostic.
Les résultats signalent le franchissement d'une condition configurée et
conservent les mesures qui le justifient.

```text
Measurement validée
       ↓
Patient → profils → règles sélectionnées
       ↓
Historique récent isolé par patient
       ↓
ThresholdRule / CombinedRule / TrendRule
       ↓
Résultat : règle + profils + sévérité + preuves
       ↓
AlertEngine du prototype
```

## Correspondance UML et fichiers

| Classe ou composant | Fichier | Responsabilité |
| --- | --- | --- |
| `MonitoringRule` | `src/domain/monitoring_rule.py` | Classe abstraite, identifiant, sévérité, fenêtre et évaluation |
| `ThresholdRule` | Même fichier | Comparaison d'une mesure à un seuil |
| `CombinedRule` | Même fichier | Conjonction de plusieurs conditions synchronisées |
| `TrendRule` | Même fichier | Évolution monotone d'un paramètre dans le temps |
| `Condition` | Même fichier | Paramètre, opérateur et seuil d'une combinaison |
| `RuleContext` | Même fichier | Historique disponible et instant d'évaluation |
| Catalogue | `config/monitoring-rules.json` | Valeurs de démonstration et affectation aux profils |
| Chargement | `src/domain/rule_catalog.py` | Construction des règles et contrôle de la configuration |
| Profils | `src/domain/clinical_profile.py` | Règles par défaut et personnalisation |
| `AnomalyDetector` | `src/processing/anomaly_detector.py` | Validation, historique, sélection et évaluation |
| Passage aux alertes | `src/processing/alert_engine.py` | Sévérité et provenance de la règle |

Les règles et leurs conditions sont des objets immuables. Le catalogue est lu
lors de la création du détecteur pour les règles communes et lors de la
création des profils pour leurs règles. Modifier le JSON nécessite donc de
recréer ces objets ou de relancer le programme Python.

## Règles de démonstration fournies

Les unités sont celles du modèle de données. Les comparaisons strictes et
inclusives indiquées ci-dessous correspondent exactement au code.

| Source | Identifiant | Condition | Sévérité |
| --- | --- | --- | --- |
| Commun | `high_heart_rate` | HR > 100 bpm | WARNING |
| Commun | `low_spo2` | SpO₂ < 95 % | WARNING |
| Commun | `high_temperature` | Température > 37,5 °C | WARNING |
| Commun | `combined_cardiopulmonary_anomaly` | HR > 100 et SpO₂ < 95 | CRITICAL |
| Diabète | `diabetes_glucose_low` | Glycémie < 70 mg/dL | CRITICAL |
| Diabète | `diabetes_glucose_high` | Glycémie > 180 mg/dL | WARNING |
| Hypertension | `hypertension_systolic_high` | Systolique ≥ 140 mmHg | WARNING |
| Hypertension | `hypertension_diastolic_high` | Diastolique ≥ 90 mmHg | WARNING |
| Hypertension | `hypertension_systolic_rising` | Hausse strictement progressive d'au moins 15 mmHg | WARNING |
| Anxiété/stress | `anxiety_rest_pattern` | HR > 100, HRV < 30 ms, respiration > 20/min et activité ≤ 0,2 | WARNING |

Les quatre règles communes reprennent le comportement illustratif du prototype.
Elles s'appliquent aussi à un patient sans profil. Une activité élevée empêche
le pattern de stress, mais ne désactive pas la règle commune de fréquence
cardiaque. Le catalogue n'est pas exhaustif et ne couvre pas toutes les anomalies
possibles : absence de résultat ne signifie pas absence de problème.

Pour le diabète, les repères 70/180 sont décrits dans la page
[NIDDK — Managing Diabetes](https://www.niddk.nih.gov/health-information/diabetes/overview/managing-diabetes),
qui précise que les cibles dépendent des personnes et du contexte. Leur emploi
ici, les niveaux de sévérité et les fenêtres sont des choix de démonstration,
pas une validation médicale du prototype.

Les valeurs de pression ne posent aucun diagnostic : le contexte et des mesures
répétées comptent, comme l'explique l'[American Heart Association](https://newsroom.heart.org/news/the-lowdown-on-high-blood-pressure-what-you-need-to-know).
La combinaison de stress, le seuil HRV et l'indice local d'activité sont
illustratifs ; leur message dit explicitement **sans diagnostic d'anxiété**.

## Fonctionnement des trois familles

### Seuil

`ThresholdRule` supporte `>`, `>=`, `<`, `<=` et `==`. Elle compare la valeur
la plus récente du paramètre dans la fenêtre. Aucun opérateur n'est exécuté
par `eval` : les opérations autorisées sont explicites.

La fenêtre par défaut est de 120 secondes, compatible avec la validation de
l'étape 5. Un résultat n'est émis que si sa preuve contient une nouvelle mesure
acceptée pendant l'appel ; un paramètre sans rapport ne réémet pas une ancienne
anomalie.

### Combinaison

`CombinedRule` exige que **toutes** ses conditions soient satisfaites. Les
règles fournies utilisent une fenêtre de 30 secondes et un écart maximal de
10 secondes entre la mesure la plus ancienne et la plus récente.

Si un paramètre manque, est trop ancien ou dépasse cet écart, la combinaison
ne déclenche pas. Les paramètres peuvent venir d'appareils différents du même
patient. Une règle personnalisée peut demander `same_reading=True` : les preuves
doivent alors partager appareil, `reading_id` et horodatage, ce qui convient à
une paire systolique/diastolique.

Cette option vérifie le lien entre lectures, pas une comparaison entre les deux
valeurs. La validation complète des paires reçues, indépendamment des règles,
reste un raccordement distinct. Les deux seuils d'hypertension fournis s'évaluent
séparément et n'attendent pas une paire.

### Tendance

La règle systolique fournie utilise :

- une fenêtre de **60 secondes** ;
- au moins **3 mesures**, espacées sur au moins **10 secondes** au total ;
- un écart maximal de **30 secondes** entre deux mesures successives ;
- une hausse **strictement monotone** sur les échantillons retenus ;
- une augmentation totale d'au moins **15 mmHg**.

Les échantillons proviennent du **même appareil**. Le moteur sélectionne
l'appareil de la mesure la plus récente de ce paramètre et utilise ses mesures
dans la fenêtre. Il ne fabrique pas une tendance en mélangeant deux capteurs.
Une rafale très courte, des doublons, un plateau puis un seul saut, ou un
intervalle trop long ne suffisent pas.

`TrendRule` permet aussi `direction="decreasing"`. Il s'agit d'une règle simple
sur les valeurs de la fenêtre, sans régression statistique ni estimation de
pente. Une oscillation dans la fenêtre empêche une tendance strictement monotone.

## Personnalisation d'un profil

```python
from src.domain import Patient, DiabetesProfile, ThresholdRule

rule = ThresholdRule(
    rule_id='custom_glucose_demo',
    parameter='glucose', operator='>', threshold=200,
    severity='WARNING', message='Seuil personnalisé de démonstration franchi.',
)
patient = Patient('P001', 'Patient 1', profiles=[DiabetesProfile(rules=[rule])])
```

Passer `rules=[]` désactive les règles propres à ce profil ; les règles communes
du détecteur restent présentes. Un `ClinicalProfile` générique conserve une
liste vide par défaut. `get_rules()` retourne une copie de la liste.

Le détecteur relit les profils du patient à chaque appel : un retrait de profil
prend effet à la mesure suivante. Une même règle partagée par plusieurs profils
est évaluée une seule fois et liste toutes ses sources. Deux règles ayant le
même identifiant mais des définitions différentes provoquent une erreur de
configuration explicite.

## API et intégration Python

```python
from src.domain import Measurement, Patient, DiabetesProfile
from src.processing import AnomalyDetector

patient = Patient('P001', 'Patient 1', profiles=[DiabetesProfile()])
measurement = Measurement(
    'M001', 'P001', device_id='SIM_GLUCOSE',
    parameter='glucose', value=220, unit='mg/dL', quality='valid',
)
detector = AnomalyDetector()
results = detector.detect(measurement, patient)
print(results)
```

- `detect(measurement, patient)` traite une mesure et réutilise le contexte récent.
- `detect_batch(measurements, patient)` valide tout un cycle avant de modifier
  l'historique, puis évalue chaque règle une seule fois sur le résultat du cycle.
- `detect_payload(payload, patient, topic=None)` valide les données reçues, y
  compris leurs métadonnées originales, avant de créer la mesure interne.
- `clear_patient(patient_id)` libère l'historique et les identifiants mémorisés.

`detect()` sans patient est conservé pour les anciens exemples : il applique
uniquement les règles communes. Les anciens lots locaux `values={...}` sont
adaptés en mesures scalaires internes ; ils ne redeviennent pas admis sur MQTT.
Depuis l'étape 7, `main.py` utilise `evaluate_batch()` et les vrais profils de
P001 pour obtenir aussi les résultats non déclenchés ou indéterminés, nécessaires
à la gestion des alertes. Son ancien lot temporaire a été supprimé.

Les méthodes de compatibilité `detect_combined_anomaly()` et `detect_trend()`
consomment elles aussi la mesure, puis filtrent les résultats. Ne pas les appeler
successivement sur la même observation après `detect()` : celle-ci serait déjà
consommée. Préférer un appel à `detect()` et filtrer le champ `kind` du résultat.

## Historique, doublons et rejets

Chaque patient possède son propre historique en mémoire. Un message ne peut pas
être attribué à un autre patient que celui fourni à l'appel. Les mesures sont
copiées afin qu'une modification ultérieure de l'objet source ne réécrive pas
les preuves déjà mémorisées.

La durée de rétention suit `max_age_seconds` de la validation, soit 120 secondes.
Une règle ne peut pas demander une fenêtre supérieure. Le nombre de mesures et
le cache d'identifiants sont limités à **2048 éléments par patient** par défaut,
configurables via `max_history`. À forte cadence, cette limite peut raccourcir
l'historique effectivement disponible.

- Un même `measurement_id` et même contenu ne déclenche pas à nouveau.
- Une même lecture `(appareil, paramètre, reading_id)` n'est pas réinsérée avec
  un nouvel identifiant de message si son contenu reste identique.
- Réutiliser un de ces identifiants avec un contenu différent provoque une erreur.
- Une mesure antérieure ou de même date que la dernière du même appareil et
  paramètre est ignorée : elle ne remplace pas l'état courant.
- Une mesure invalidée ou un cycle contenant une mesure invalide ne modifie pas
  l'historique. `detect_batch()` est atomique pour ses mises à jour internes.

Cette déduplication est limitée à la mémoire récente. Elle ne remplace pas une
contrainte d'unicité en base. Un redémarrage oublie l'historique. Les appels sont
prévus pour un traitement séquentiel, pas pour plusieurs threads partageant le
même détecteur sans synchronisation.

Si `monitoring_enabled=False` lors d'un appel au moteur, celui-ci efface le
contexte du patient et n'émet aucun résultat. Si l'application suspend toute
livraison sans appeler le moteur, elle peut appeler `clear_patient()` pour
marquer explicitement cette interruption ; sinon la rétention temporelle
continue de limiter les anciennes données.

## Résultats et passage aux alertes

Chaque résultat contient `rule_id`, `kind`, `patient_id`, `profile_ids`,
`severity`, `message`, `timestamp` et les preuves (`evidence`) avec identifiants,
appareils, valeurs, unités et dates. Le champ `type` reprend le `rule_id` pour la
compatibilité du prototype. Une preuve de tendance contient tous les échantillons
retenus, tandis que `value` expose la dernière valeur par paramètre.

`AlertEngine` reprend la sévérité configurée par la règle. Les alertes conservent
`rule_id`, `profile_ids` et `measurement_ids`. Leurs identifiants sont maintenant
des UUID afin d'éviter les collisions entre cycles. Les anciens dictionnaires
d'anomalies restent supportés avec leur ancienne attribution de sévérité.

La [gestion des épisodes est disponible à l'étape 7](step7_alerts_states.md) :
plusieurs nouvelles mesures anormales actualisent la même alerte active par
patient et règle. Les méthodes `detect*()` continuent de retourner uniquement
les correspondances. Pour résoudre automatiquement les alertes après des
confirmations de récupération, utiliser le rapport complet de `evaluate_batch()`
ou `evaluate_payload()`, puis `AlertEngine.process()`.

## Démonstrations et tests

```sh
# Démonstration déterministe, sans Docker, avec horloge virtuelle.
.venv/bin/python -m examples.step6_rules

# Mesures simulées → Mosquitto → validation Node-RED → règles Python → alertes.
docker compose up -d --wait
.venv/bin/python -m examples.step6_rules --mqtt

# Prototype P001 avec règles par profils.
.venv/bin/python main.py --storage memory --no-mqtt --cycles 2

# Tests locaux et intégration complète.
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q --mqtt-integration
```

Le mode local illustre les différences entre profils, la progression systolique
110 → 120 → 130 sur dix secondes virtuelles, le contexte activité/repos et un
doublon ignoré. Il n'attend pas dix secondes réelles.

Le mode MQTT attend **sept mesures de deux patients**, reçues et validées par
Node-RED, puis **cinq déclenchements** : glycémie élevée, systolique élevée,
diastolique élevée, fréquence cardiaque élevée et pattern physiologique au
repos. Il construit cinq alertes de démonstration et vérifie leurs résultats.
Les options `--broker` et `--port` permettent de changer le broker de cet exemple.

Les règles s'exécutent en Python. Node-RED conserve son rôle de validation et de
transport des mesures ; le consommateur de l'exemple utilise le topic technique
`/received`. Il s'agit d'une démonstration finie, pas encore d'un service backend
permanent. Dans `main.py`, l'analyse locale reste indépendante du reçu Node-RED.

Les tests couvrent notamment les profils cumulés, les comparateurs exacts,
l'activité, les données manquantes ou désynchronisées, les tendances, les
appareils distincts, les doublons, l'ordre temporel, l'atomicité des cycles, la
rétention et la provenance des alertes. Le test d'intégration exerce réellement
le trajet MQTT → Node-RED → moteur de règles Python.
