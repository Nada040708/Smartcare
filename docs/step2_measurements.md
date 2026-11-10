# Étape 2 — Paramètres et mesures

## Paramètres disponibles

Les huit classes héritent de `PhysiologicalParameter`. Elles génèrent des
valeurs de démonstration et conservent l'instant de la lecture en UTC.

| Classe | Identifiant de mesure | Unité | Intervalle de génération de démonstration |
| --- | --- | --- | --- |
| `HeartRate` | `heart_rate` | `bpm` | 60–100 |
| `SpO2` | `spo2` | `%` | 95–100 |
| `Temperature` | `temperature` | `°C` | 36–37,5 |
| `BloodPressure` | `systolic_bp`, `diastolic_bp` | `mmHg` | 110–130 / 70–85 |
| `Glucose` | `glucose` | `mg/dL` | 80–130 |
| `RespiratoryRate` | `respiratory_rate` | `breaths/min` | 12–20 |
| `HRV` | `hrv` | `ms` | 30–70 |
| `Activity` | `activity` | `1` (sans dimension) | 0–1 |

Ces intervalles servent à générer des données fictives. Ils ne constituent pas
des seuils cliniques. Les attributs historiques `normal_min`, `normal_max` et
`is_normal()` sont conservés pour le prototype ; le moteur de règles par profil
sera développé séparément.

`HRV` représente ici un RMSSD simulé, sans calcul à partir d'intervalles RR.
`Activity` est un indice local fictif : 0 = repos, 1 = activité élevée. Il ne
représente ni des pas, ni des MET, ni une échelle médicale validée.

## Nouveau format de mesure

Une `Measurement` contient un seul paramètre numérique et son contexte.

```python
from src.domain import Measurement

measurement = Measurement(
    measurement_id="M001",
    patient_id="P001",
    device_id="SIM_GLUCOSE_01",
    parameter="glucose",
    value=130.0,
    unit="mg/dL",
    quality="valid",
    device_type="simulator",
)

assert measurement.validate()
print(measurement.to_json())
```

La date par défaut est en UTC avec fuseau. Une date fournie doit avoir un
fuseau ; son décalage est conservé dans le JSON. `reading_id` identifie la
lecture d'origine ; il vaut `measurement_id` par défaut lors d'une création
manuelle.

La validation vérifie les identifiants, le paramètre connu, son unité exacte,
la date, la qualité et une valeur numérique finie. Elle refuse notamment les
booléens, NaN et les infinis. Elle ne convertit pas les unités. Une valeur
anormale, comme une fréquence cardiaque de 145 bpm, reste sérialisable pour
que le moteur de règles puisse ensuite l'analyser.

Les qualités applicatives acceptées sont `good` (compatibilité), `valid`,
`questionable` et `invalid`. Ce sont des libellés locaux, pas les indicateurs
binaires normalisés IEEE. Une qualité `invalid` peut être transportée et
archivée : `validate()` contrôle la structure, pas l'exploitabilité clinique.
Depuis [l'étape 5](step5_validation.md), le validateur du flux n'admet que
`valid` et `good` dans le chemin d'analyse ; `questionable` et `invalid` sont rejetées.

## Conversion depuis un paramètre

```python
from src.domain.parameters import BloodPressure

pressure = BloodPressure()
pressure.generate()
systolic, diastolic = pressure.to_measurements("P001", "SIM_BP_01")

assert systolic.reading_id == diastolic.reading_id
assert systolic.timestamp == diastolic.timestamp
print(systolic.to_json())
print(diastolic.to_json())
```

`generate()` enregistre la valeur, la date et un nouvel identifiant de lecture.
`to_measurements()` exporte cette lecture sans en générer une autre. Les
identifiants des mesures sont des UUID distincts ; ceux des lectures sont
également des UUID. Les mesures déjà créées ne changent pas à la génération
suivante. Depuis l'étape 3, `record_value()` enregistre et valide une sortie de
stratégie en actualisant son contexte. Ne pas modifier directement `value` pour
simuler une nouvelle lecture, car l'horodatage ne serait pas actualisé.

La pression artérielle produit deux mesures scalaires, de même patient,
appareil, date et `reading_id`, avec deux `measurement_id` différents. Les deux
composantes sont obligatoires ; leur export exige `0 < diastolique < systolique`.

## Périmètre IEEE 11073 retenu à cette étape

Le périmètre est une **correspondance partielle avec la nomenclature
ISO/IEEE 11073-10101**, portée dans le JSON applicatif. Il n'y a pas encore de
pile IEEE 11073-20601, d'encodage binaire ni de spécialisation d'appareil 104xx.
Ce prototype ne revendique donc pas une conformité IEEE 11073 complète.

Chaque mesure structurée expose `ieee11073_metadata`. La date et la qualité
sont dérivées de la mesure afin de ne pas avoir deux valeurs contradictoires.
`device_type` est un libellé applicatif (`simulator` dans cet exemple), pas un
code normalisé de spécialisation d'appareil.

Les codes MDC décimaux complets vérifiés et implémentés sont :

| Paramètre | Code métrique / référence | Code unité / référence |
| --- | --- | --- |
| SpO₂ | `150456` / `MDC_PULS_OXIM_SAT_O2` | `262688` / `MDC_DIM_PERCENT` |
| Pression systolique non invasive | `150021` / `MDC_PRESS_BLD_NONINV_SYS` | `266016` / `MDC_DIM_MMHG` |
| Pression diastolique non invasive | `150022` / `MDC_PRESS_BLD_NONINV_DIA` | `266016` / `MDC_DIM_MMHG` |

Sources primaires consultées :

- [HL7 — nomenclature MDC et représentation des codes](https://hl7.org/fhir/R4/mdc.html).
- [HL7 — exemple SpO₂ et unité en pourcentage](https://hl7.org/fhir/R4/devicemetric-example.xml.html).
- [ITU-T H.830.6 — exemple de pression artérielle, TP/WAN/REC/PCD-01-DATA/BPM/BV-000](https://www.itu.int/rec/dologin_pub.asp?id=T-REC-H.830.6-201501-S%21%21PDF-E&lang=e&type=items).

Pour les autres paramètres, `mapping_status` vaut `unmapped` et les codes sont
`null`. Cela indique une correspondance restant à vérifier, pas l'absence d'un
code dans le standard. Il faudra notamment préciser les modalités de mesure
de la glycémie, de la température et de la fréquence cardiaque. L'indice
d'activité reste une convention locale. Aucun code n'est inventé.

## Compatibilité et prochaine étape

L'ancien constructeur `Measurement(..., values={...})` reste accepté et conserve
son JSON de lot. Il n'acquiert pas artificiellement un appareil ou un code MDC.
Mélanger `values` et `parameter/value/unit` dans le même appel est interdit.

Une mesure structurée expose aussi une vue `.values` pour les lectures faites
par le détecteur, le stockage et le dashboard existants. Le format JSON nouveau
utilise `parameter`, `value`, `unit`, pas `values`.

Depuis l'étape 3, `main.py` et `SensorSimulator` produisent le format structuré.
L'exemple de l'étape 2 reste indépendant et fonctionne sans broker MQTT :

```sh
.venv/bin/python -m examples.step2_measurements
.venv/bin/python -m pytest -q tests/domain tests/processing tests/repositories tests/dashboard
```

Le raccordement des stratégies, des deux composantes de tension et de
`monitoring_enabled` est décrit dans [l'étape 3](step3_simulation.md). Depuis
[l'étape 6](step6_rules.md), le détecteur utilise une fenêtre de mesures par
patient pour les combinaisons et tendances. `main.py` lui transmet directement
les mesures scalaires du cycle courant, sans créer de lot historique temporaire.
