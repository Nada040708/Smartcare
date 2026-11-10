# Étape 7 — États de surveillance et cycle de vie des alertes

## Objectif

Transformer les résultats des règles de l'étape 6 en **épisodes d'alerte** et en
un **état de surveillance par patient**. Une anomalie persistante actualise une
alerte existante. Une récupération confirmée la résout ; une récidive ouvre un
nouvel épisode, avec un autre identifiant.

Les règles, sévérités et confirmations restent des choix de démonstration.
`NORMAL` signifie que les règles configurées sont évaluables et non déclenchées,
sans alerte active ; ce n'est pas une conclusion médicale sur le patient.

```text
Mesures validées + profils
           ↓
AnomalyDetector.evaluate_batch() / evaluate_payload()
           ↓
Rapport : MATCHED / CLEAR / UNKNOWN, preuves et nouveauté
           ↓
AlertEngine.process()
           ↓
Création / actualisation / confirmation de récupération / résolution
           ↓
AlertRepository en mémoire + MonitoringStateManager
           ↓
Dashboard console : alertes et états par patient
```

## Classes et correspondance avec l'UML

| Élément | Fichier | Rôle |
| --- | --- | --- |
| `MonitoringState` | `src/domain/monitoring_state.py` | Les cinq valeurs de l'UML |
| `MonitoringStateManager` | `src/processing/monitoring_state_manager.py` | Calcul et mémorisation de l'état par patient |
| `Alert` | `src/domain/alert.py` | Épisode, dates, occurrences et résolution |
| `AlertEngine` | `src/processing/alert_engine.py` | Une alerte active par couple patient/règle |
| `MonitoringEvaluation`, `RuleEvaluation` | `src/domain/monitoring_evaluation.py` | Rapports internes nécessaires pour distinguer récupération et données manquantes |
| `AlertRepository` | `src/repositories/alert_repository.py` | Historique en mémoire, insertion ou mise à jour par identifiant |
| Démonstration | `examples/step7_alerts.py` | Scénario multipatient local ou via MQTT |

Comme aux étapes précédentes, les nouvelles méthodes suivent la convention
Python : `evaluateState()` devient `evaluate_state()`, `returnToNormal()` devient
`return_to_normal()` et `resolveAlert()` devient `resolve_alert()`.
Le `currentState` de l'UML est décliné par patient dans `current_states`.

## Pourquoi un rapport plus complet ?

Une liste d'anomalies vide peut signifier une valeur normale, un doublon ou
l'absence de données. Elle ne suffit donc pas pour résoudre les alertes.

| Résultat d'une règle | Signification | Conséquence |
| --- | --- | --- |
| `MATCHED` | Données exploitables et condition déclenchée | Créer/actualiser si de nouvelles preuves sont présentes |
| `CLEAR` | Données exploitables et condition non déclenchée | Peut confirmer une récupération avec des preuves renouvelées |
| `UNKNOWN` | Données absentes, expirées, désynchronisées ou historique insuffisant | Garder l'alerte et remettre les confirmations à zéro |

Le champ `fresh` indique qu'au moins une preuve a été ajoutée lors de l'appel.
Les doublons, mesures ignorées car anciennes, paramètres sans rapport et appels
vides ne constituent pas une nouvelle confirmation. Un historique encore frais
reste exploitable jusqu'à expiration : un cycle vide ne signifie pas à lui seul
une panne. Appeler périodiquement `evaluate_batch([], patient)` permet de faire
apparaître l'expiration même si aucun message n'arrive.

`get_evidence()` expose les observations exploitables d'une règle même lorsque
sa condition est fausse. Une tendance avec un nombre suffisant de points mais
un plateau peut ainsi être `CLEAR`. Une tendance avec un trou temporel ou trop
peu de points est `UNKNOWN`. Pour une nouvelle sous-classe personnalisée, il faut
implémenter cette méthode pour permettre la résolution automatique ; son
comportement par défaut ne déduit pas la récupération d'un résultat vide.

## Cycle de vie d'un épisode

La clé de déduplication est **`(patient_id, rule_id)`**, pas le texte du message.
Deux règles ayant le même message restent deux alertes distinctes.

1. Première correspondance : création immédiate d'une alerte `ACTIVE` avec UUID.
2. Nouvelle correspondance : même identifiant, preuves et date actualisées,
   compteur `occurrences` incrémenté, confirmations de récupération remises à zéro.
3. Première observation exploitable non déclenchée : l'alerte reste `ACTIVE`,
   `recovery_count` passe à 1.
4. Deuxième confirmation : l'alerte devient `RESOLVED`, avec date et motif
   `RECOVERY_CONFIRMED` ; elle reste consultable dans l'historique.
5. Nouvelle anomalie après résolution : nouvel identifiant, nouvel épisode.

Le nombre de confirmations est configurable : `AlertEngine(recovery_confirmations=2)`.
Ce sont des observations, **pas une durée minimale**. Une nouvelle anomalie,
un résultat `UNKNOWN`, une suspension ou une déconnexion explicitement signalée
interrompent la confirmation. Un doublon n'incrémente pas le compteur.

Pour une combinaison, **chaque paramètre doit avoir une observation plus récente**
que celle de la dernière correspondance, puis de la précédente confirmation.
Les messages peuvent arriver séparément : le contexte les rassemble. Répéter
seulement SpO₂ ne permet pas de compter deux fois une ancienne fréquence
cardiaque redevenue normale. Pour une tendance, on compare la date du dernier
point du paramètre ; les anciens points de la fenêtre restent nécessaires.

`occurrences` compte les évaluations déclenchées avec nouvelles preuves, pas
les cycles du simulateur. Une combinaison peut être actualisée plusieurs fois
pendant un cycle reçu paramètre par paramètre, tout en conservant une seule alerte.

Les champs de l'alerte comprennent :

- `timestamp` : ouverture ; `last_seen_at` : dernière correspondance ;
- `rule_id`, `parameter`, `profile_ids`, `severity`, `message` ;
- `measurement_ids` : preuves de la dernière correspondance ;
- `occurrences`, `recovery_count`, `recovery_measurement_ids` : dernières preuves
  de confirmation ;
- `resolved_at`, `resolution_reason` : date et motif de résolution.

Les dates d'évaluation sont en UTC dans les démonstrations. `resolve()` est
idempotente : rappeler la méthode ne réécrit pas une résolution existante.
`resolve_alert(patient_id, rule_id, timestamp=None, reason='MANUAL')` permet une
résolution explicite. Cette méthode interne ne constitue pas encore une action
authentifiée du dashboard.

Retirer un profil, supprimer une règle ou désactiver la surveillance ne prouve
pas la disparition de l'anomalie : l'alerte est conservée. Une décision explicite
peut la clôturer avec un motif tel que `RULE_REMOVED`, distinct d'une récupération.

## États du patient

Le moteur d'alertes est traité avant le gestionnaire d'états. Ce dernier prend
en compte les alertes encore actives, y compris pendant la confirmation.

| État | Condition |
| --- | --- |
| `DISCONNECTED` | Signal technique explicite `connected=False` ; priorité d'affichage |
| `CRITICAL` | Au moins une alerte active de sévérité `CRITICAL` |
| `ALERT` | Sinon, au moins une alerte active `WARNING` |
| `SURVEILLANCE` | Alerte `INFO`, données incomplètes, aucune règle, surveillance suspendue ou reprise non confirmée |
| `NORMAL` | Aucune alerte active, surveillance activée, au moins une règle, toutes les règles `CLEAR` avec preuves exploitables après une éventuelle déconnexion |

Le retrait d'une alerte critique peut faire redescendre vers `ALERT` si une
autre alerte reste active. L'état initial sans données est `SURVEILLANCE`.
`return_to_normal()` réutilise ces contrôles ; elle ne force pas l'état.
La couverture porte sur les règles configurées, pas sur tous les paramètres
physiologiques possibles. Une tendance encore en phase de constitution de
l'historique empêche ainsi `NORMAL`, même si les seuils simples sont satisfaits.

Une déconnexion conserve les alertes physiologiques. À la reprise, leurs
sévérités redeviennent visibles et le retour à `NORMAL` nécessite des preuves
postérieures à la déconnexion. Les confirmations reprennent à zéro.

**Le détecteur automatique de timeout `ConnectionMonitor` et les événements
techniques de panne/reprise restent prévus à l'étape 11.** Ici, le signal est
fourni explicitement au moteur et au gestionnaire d'états. La démonstration ne
coupe pas réellement Mosquitto et ne simule pas un timeout réseau.

## Utilisation dans le code

```python
from src.domain import Patient
from src.processing import AnomalyDetector, AlertEngine, MonitoringStateManager
from src.repositories import AlertRepository

patient = Patient('P001', 'Patient fictif')
detector = AnomalyDetector()
engine = AlertEngine(recovery_confirmations=2)
states = MonitoringStateManager()
repository = AlertRepository()

# À chaque cycle, fournir la liste des mesures scalaires reçues/validées.
# Un cycle vide est permis, notamment pour réévaluer la fraîcheur.
measurements = []
report = detector.evaluate_batch(measurements, patient)
connected = True  # Futur signal de ConnectionMonitor.
for alert in engine.process(report, connected=connected):
    repository.save(alert)
state = states.evaluate_state(report, engine.get_active(), connected=connected)
print(state.value)  # SURVEILLANCE sans données.
```

Pour un message réseau, utiliser `evaluate_payload(payload, patient, topic=...)` :
la validation du JSON original et de ses métadonnées précède la reconstruction.
Les méthodes `detect*()` de l'étape 6 continuent de renvoyer une liste d'anomalies.
**Choisir un seul chemin d'ingestion** : ne pas appeler `detect()` puis
`evaluate_batch()` sur les mêmes observations, car elles seraient déjà consommées.

L'ancienne méthode `AlertEngine.evaluate(patient_id, anomalies)` reste utilisable
pour ouvrir et actualiser les alertes. Une liste vide ne résout rien ; la
résolution automatique nécessite le rapport complet et `process()`.

Un numéro de séquence et l'identifiant de l'instance du détecteur protègent
contre le retraitement d'un rapport. Conserver les mêmes instances de détecteur,
moteur et gestionnaire pendant une session ; les rapports se traitent dans
l'ordre. Remplacer le détecteur seul provoque une erreur explicite. Le
rétablissement du contexte après redémarrage sera à traiter avec la persistance.

`main.py` utilise désormais ce circuit, y compris pour les cycles vides. Le
dashboard console ajoute `patient_states` à ses compteurs. Avec MQTT activé,
`main.py` analyse toujours localement les mesures qu'il publie ; l'exemple
ci-dessous, en mode `--mqtt`, analyse les reçus effectivement renvoyés par Node-RED.

## Démonstration et vérification

```sh
# Horloge virtuelle : pas de Docker ni d'attente entre les cycles.
.venv/bin/python -m examples.step7_alerts

# Même scénario avec le trajet MQTT → Mosquitto → Node-RED → Python.
docker compose up -d --wait
.venv/bin/python -m examples.step7_alerts --mqtt

# Prototype et tests.
.venv/bin/python main.py --storage memory --no-mqtt --cycles 2 --interval 0.01
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q --mqtt-integration
```

P001 et P002 ont ici le profil diabète et reçoivent HR, SpO₂, température et
glycémie. P002 reste `NORMAL`. Le déroulement attendu pour P001 est :

| Phase | État | Alertes actives | Épisodes dans l'historique |
| --- | --- | --- | --- |
| Normal | NORMAL | 0 | 0 |
| Anomalie brutale | CRITICAL | 4 | 4 |
| Anomalie persistante | CRITICAL | 4 | 4 |
| Déconnexion explicitement signalée | DISCONNECTED | 4 | 4 |
| Première confirmation de récupération | CRITICAL | 4 | 4 |
| Doublon des mêmes mesures | CRITICAL | 4 | 4 |
| Deuxième confirmation | NORMAL | 0 | 4 |
| Récidive | CRITICAL | 4 | 8 |

Les quatre alertes concernent HR, SpO₂, leur combinaison et la glycémie. Le mode
MQTT vérifie **56 reçus Node-RED**, dont huit répétitions intentionnelles de
mesures déjà traitées. Les options `--broker` et `--port` sont disponibles.
Il s'agit d'un consommateur de démonstration fini, pas d'un backend permanent.

Les tests couvrent les états, les épisodes et récidives, les confirmations,
les doublons et rapports rejoués, les données anciennes ou invalides, les
combinaisons asynchrones, les tendances incomplètes, la suspension, le retrait
d'un profil, les déconnexions explicites et l'isolation des patients. Le test
d'intégration vérifie le scénario sur les vrais services locaux.

## Limites et prochaine étape

Les exemples propres à l'étape 7 restent en mémoire. Depuis
[l'étape 8](step8_postgresql.md), `main.py` utilise PostgreSQL par défaut : les
mesures, épisodes et événements sont persistants, les alertes actives sont
restaurées et les confirmations repartent à zéro après un redémarrage.
L'historique du détecteur est reconstitué avec les nouvelles observations.
Le mode `--storage memory` conserve le fonctionnement de cette étape.
Les notifications externes et l'interface d'acquittement restent à réaliser.
