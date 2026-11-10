# Étape 5 — Validation des données reçues

## Objectif

Vérifier qu'une mesure est exploitable avant de la transmettre à l'analyse.
Une mesure **acceptée** n'est pas nécessairement **normale** : 145 bpm, ou une
SpO₂ de 50 %, traversent la validation et doivent être interprétés ensuite par
les règles de surveillance. Une unité incorrecte, un timestamp ancien ou une
qualité insuffisante provoquent en revanche un rejet technique explicite.

Cette étape n'implémente pas de diagnostic, de règle clinique ni de résolution
d'alerte. Les limites numériques ci-dessous sont des choix de démonstration,
non des seuils médicaux validés ni des spécifications certifiées de capteurs.

## Architecture et fichiers

```text
Simulateur → MQTT → Mosquitto → Node-RED JSON
                                     ↓
                               DataValidator
                               ↙           ↘
                          accepté          rejeté
                            ↓                ↓
                   Debug + /received  Debug + /rejected
```

| Fichier | Responsabilité |
| --- | --- |
| `config/validation-policy.json` | Politique partagée : unités, bornes, temps, qualités et codes MDC connus |
| `src/processing/data_validator.py` | Validation Python, méthodes UML et résultats structurés |
| `infra/node-red/validator.cjs` | Même politique appliquée à la réception Node-RED |
| `infra/node-red/settings.js` | Chargement du module dans `functionGlobalContext` |
| `infra/node-red/flows.json` | Routage séparé des mesures acceptées et des rejets |
| `tests/fixtures/validation_cases.json` | 66 cas contractuels communs aux deux implémentations |
| `examples/step5_validation.py` | Test réel de huit décisions de validation via MQTT |

Le code existe dans les deux langages pour exécuter la validation localement en
Python et dans Node-RED sans ajouter prématurément un service backend. La
politique est commune et les mêmes cas vérifient les deux implémentations.
Un test vérifie aussi la cohérence des unités et codes MDC avec le modèle du
domaine. Aucun nouveau code IEEE n'est attribué à cette étape.

## Contrôles du message structuré

1. Le JSON doit être décodable et contenir un objet, sans l'ancien champ `values`.
2. Les identifiants, le paramètre, l'unité, la date et la qualité doivent être des
   chaînes non vides. La valeur doit être un nombre fini ; booléens, chaînes,
   `null`, NaN et infinis sont refusés.
3. Le paramètre doit être connu et l'unité exactement celle de la politique.
   Aucune conversion d'unité n'est implicite.
4. La valeur doit respecter les limites techniques configurées, bornes incluses.
5. La date doit être un timestamp ISO avec date réelle, heure valide et fuseau
   explicite (`Z` ou décalage). Les fractions jusqu'à six chiffres sont acceptées.
6. La mesure ne doit pas dépasser l'ancienneté maximale ni la tolérance future.
7. La qualité doit être `valid` ou `good` (compatibilité du prototype).
8. Les métadonnées doivent correspondre au paramètre et à l'unité : codes,
   références, état de correspondance, nomenclature, qualité et timestamp.
9. Sur MQTT, le patient du message doit correspondre à celui du topic. Les
   messages retenus restent refusés pour cette démonstration de données courantes.

Les métadonnées reçues sont inspectées **telles quelles** ; elles ne sont pas
régénérées avant validation, ce qui masquerait une contradiction. Les codes
encore inconnus doivent être explicitement `null` avec `mapping_status=unmapped`.
Le champ `device_type` reste un libellé applicatif non vide, pas une preuve de
conformité d'un appareil IEEE.

Les champs supplémentaires sont tolérés pour permettre des extensions ; les
champs requis ne peuvent pas être remplacés par ces extensions. La qualité
`questionable` ou `invalid` est transportable par le modèle de données, mais
n'est pas admise dans le chemin d'analyse de cette étape.

## Politique par défaut

| Paramètre | Unité | Minimum technique | Maximum technique |
| --- | --- | ---: | ---: |
| `heart_rate` | `bpm` | 0 | 300 |
| `spo2` | `%` | 0 | 100 |
| `temperature` | `°C` | 20 | 50 |
| `systolic_bp` | `mmHg` | 1 | 350 |
| `diastolic_bp` | `mmHg` | 1 | 250 |
| `glucose` | `mg/dL` | 1 | 1000 |
| `respiratory_rate` | `breaths/min` | 0 | 100 |
| `hrv` | `ms` | 0 | 5000 |
| `activity` | `1` | 0 | 1 |

Ces valeurs définissent uniquement le domaine accepté par ce prototype. Elles
remplacent les anciennes bornes très étroites du validateur (par exemple SpO₂
70–100) pour laisser passer des anomalies destinées au futur moteur de règles.
Elles devront être adaptées aux appareils effectivement utilisés. Une valeur
égale à zéro pour la fréquence cardiaque ou la respiration n'est pas classée
« normale » par ce mécanisme.

- Ancienneté maximale : **120 secondes**, limite incluse.
- Avance maximale sur l'horloge de réception : **5 secondes**, limite incluse.
- Qualités acceptées : **`valid`, `good`**.

La comparaison se fait par rapport à l'heure de réception. Les décalages de
fuseau sont pris en compte ; Node-RED utilise la précision milliseconde de
JavaScript, Python conserve les microsecondes. Synchroniser les horloges reste
nécessaire. Cette politique vise les données courantes : elle ne doit pas être
utilisée telle quelle pour l'import d'historiques médicaux.

Les limites et délais se modifient dans `config/validation-policy.json`.
Redémarrer Node-RED et relancer le processus Python pour recharger la politique :

```sh
docker compose restart node-red
```

## Utilisation Python

```python
from src.domain import Measurement
from src.processing import DataValidator

measurement = Measurement(
    'M001', 'P001', device_id='SIM_HR_01',
    parameter='heart_rate', value=145, unit='bpm', quality='valid',
)
validator = DataValidator()
result = validator.validate_payload(
    measurement.to_dict(), topic='health/P001/vitals',
)
assert result.accepted
print(result.to_dict())  # {'accepted': True, 'errors': []}
```

`validate_payload()` accepte un dictionnaire, une chaîne JSON ou des octets UTF-8.
Il retourne un `ValidationResult` contenant `accepted` et une liste d'erreurs
`{code, field}`. Un message peut avoir plusieurs erreurs ; aucun résultat ne
modifie le message fourni. Les paramètres `topic` et `retained` représentent le
contexte de transport.

Les méthodes UML restent disponibles :

| UML | Python |
| --- | --- |
| `validateFormat()` | `validate_format(measurement)` |
| `validateRange()` | `validate_range(measurement)` |
| `validateTimestamp()` | `validate_timestamp(measurement)` |
| `validateQuality()` | `validate_quality(measurement)` |

`validate(measurement)` combine les contrôles et retourne un booléen. Il conserve
la compatibilité avec les lots locaux du prototype, qui sont contrôlés pour
leurs paramètres, valeurs, date et qualité mais n'ont pas de métadonnées par
valeur. Ces lots ne sont **pas** admis par `validate_payload()` sur MQTT.

`main.py` utilise désormais le résultat détaillé. Un rejet n'est ni publié,
ni stocké dans son dépôt de mesures, ni envoyé à son détecteur local.

## Résultats Node-RED et codes de rejet

L'onglet s'appelle désormais **Smartcare — Étapes 4 et 5**. Une mesure acceptée
est affichée et retournée inchangée sur `health/<patient_id>/received`.
Un rejet est affiché dans **Message rejeté** et envoyé sur
`health/<patient_du_topic_source>/rejected` :

```json
{
  "measurement_id": "M001",
  "accepted": false,
  "errors": [{"code": "unit_mismatch", "field": "unit"}]
}
```

| Code | Signification |
| --- | --- |
| `invalid_json` | JSON non décodable |
| `invalid_format` | Structure ou champ requis incorrect |
| `unknown_parameter` | Paramètre absent de la politique |
| `unit_mismatch` | Unité différente de celle attendue |
| `invalid_value` | Valeur non numérique ou non finie |
| `out_of_range` | Valeur hors limites techniques |
| `invalid_timestamp` | Date, heure ou fuseau invalide |
| `stale_timestamp` | Mesure trop ancienne |
| `future_timestamp` | Mesure trop en avance |
| `invalid_quality` | Qualité non admise pour l'analyse |
| `metadata_mismatch` | Métadonnées absentes ou contradictoires |
| `topic_mismatch` | Patient du payload différent du topic |
| `retained_message` | Ancien message retenu reçu sur le flux courant |
| `validation_unavailable` | Erreur technique empêchant l'exécution du validateur Node-RED |

Pour un JSON indécodable, l'identifiant vaut `null`. Un rejet contient les
motifs, pas une copie complète des valeurs reçues. Les rejets ne sont pas des
alertes cliniques et ne sont pas encore persistés en base.

## Démarrage, migration et démonstration

```sh
docker compose up -d --wait
.venv/bin/python -m examples.step5_validation
```

Le résultat attendu contient **une acceptation** (145 bpm) et **sept rejets** :
unité, limite technique, ancienneté, avance, qualité, métadonnées et paramètre
inconnu. L'exemple envoie volontairement des payloads bruts avec Paho pour tester
le contrôle à la réception ; il ne les fait pas passer par la validation locale
du publisher. Il utilise de nouveaux identifiants et vérifie les codes retournés.

Le flow actif de ce poste a été sauvegardé puis mis à jour en conservant ses
autres nœuds. Sur une nouvelle installation, le flow de l'étape 5 est chargé
automatiquement. Sur une installation possédant encore l'ancien flow dans le
volume Node-RED, `docker compose up` monte le module mais ne remplace pas le flow
persisté : exporter les modifications à conserver, puis importer le fichier
`infra/node-red/flows.json` en remplaçant les nœuds existants et déployer.

Le flow dépend du module et de la politique montés par Compose ; l'importer
seul dans un autre Node-RED ne suffit pas. Il faut également charger le module
dans `functionGlobalContext`, comme dans le fichier `settings.js` du projet.

Les exemples des étapes 3 et 4 restent disponibles :

```sh
.venv/bin/python main.py --storage memory --no-mqtt --cycles 2
.venv/bin/python -m examples.step4_mqtt
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q --mqtt-integration
```

## Tests et limites restant à traiter

Les 66 cas communs couvrent les bornes des neuf composantes scalaires, les
valeurs anormales admises, les formats, les dates impossibles, les limites de
fraîcheur, les fuseaux, les qualités, les métadonnées, les topics et les messages
retenus. Le test MQTT vérifie huit décisions réelles ; le trajet accepté de
l'étape 4 reste également testé.

La validation est **sans état, message par message**. La relation systolique /
diastolique est déjà vérifiée lors de la génération, mais le contrôle de deux
messages reçus ensemble nécessite leur regroupement par patient, appareil et
`reading_id` ; il n'est pas effectué par ce validateur scalaire. La déduplication,
l'ordre des messages, les patients/appareils autorisés, les absences prolongées
et le stockage des rejets restent à raccorder aux étapes concernées.

Le moteur de règles par profil est désormais implémenté dans
[l'étape 6](step6_rules.md) : seuils, combinaisons et tendances, appliqués aux
mesures validées. Son catalogue de démonstration n'est pas exhaustif. Il ajoute
une déduplication récente et le traitement temporel dans le moteur ; cela ne
remplace pas les contraintes d'unicité du futur stockage persistant.

Le chargement du module suit la [documentation Node-RED sur functionGlobalContext](https://nodered.org/docs/user-guide/writing-functions#loading-additional-modules).
