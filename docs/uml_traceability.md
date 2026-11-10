# Traçabilité du diagramme UML

Référence : [diagramme fourni](architecture.mmd). Ce tableau couvre ses 16 groupes.
Il décrit une correspondance fonctionnelle, pas une identité littérale entre
chaque nom UML et un fichier Python. Les fonctions abstraites sont implémentées
par leurs sous-classes ; aucun `TODO` applicatif n'a été trouvé lors de l'audit.

| Groupe UML | Réalisation | Preuves principales |
| --- | --- | --- |
| 1. Patient, profils et spécialisations | `src/domain/patient.py`, `clinical_profile.py` ; profils cumulables et priorités | tests patients/profils, étape 1 |
| 2. Huit paramètres | `src/domain/parameters/` et catalogue partagé `parameter_definitions.py` ; pression en deux composantes, donc neuf scalaires | tests paramètres, étape 2 |
| 3. Measurement et IEEE11073Metadata | `measurement.py`, `ieee11073_metadata.py` ; JSON structuré et nomenclature partielle | tests mesures/validation ; limites IEEE dans étape 2 |
| 4. SensorDevice, SensorSimulator, stratégies | `src/simulation/` ; normal, progressif, brutal, manque, récupération et panne/reprise | tests simulation, étape 3 |
| 5. Publisher, Subscriber, broker | `mqtt_publisher.py` ; MQTT IN de Node-RED et `web/receiver.py` remplissent les rôles d'abonné ; Mosquitto dans Compose | intégrations MQTT et TLS |
| 6. TLSService, MQTTAuthentication | `communication/tls.py`, certificats privés, comptes/ACL Mosquitto | tests TLS/ACL et certificats |
| 7. NodeREDFlow, DataValidator | `infra/node-red/`, `processing/data_validator.py`, politique JSON partagée | tests flow JavaScript et validation Python |
| 8. MonitoringRule et trois familles | `domain/monitoring_rule.py`, `rule_catalog.py`, `config/monitoring-rules.json` | tests seuils/combinaisons/tendances |
| 9. AnomalyDetector | `processing/anomaly_detector.py` ; mémoire bornée par patient, fraîcheur et preuves des règles | `test_profile_rules.py` |
| 10. MonitoringStateManager / enum | `monitoring_state_manager.py`, `domain/monitoring_state.py` | tests cycle d'alerte et connexion |
| 11. AlertEngine / Alert | `processing/alert_engine.py`, `domain/alert.py` ; épisodes, gravité, déduplication, résolution | tests cycle de vie et persistance |
| 12. ConnectionMonitor / TechnicalEvent | `processing/connection_monitor.py`, `technical_event.py`, surveillance permanente dans le récepteur | tests temporisations, reprise, manques et navigateur |
| 13. Trois repositories | interfaces locales dans `src/repositories/`, versions PostgreSQL dans `postgres_repositories.py` ; transactions communes | `tests/storage/test_postgres.py` |
| 14. EncryptionService, Consent, AuditLog | `security/encryption.py`, `domain/consent.py`, `consent_repository.py`, audit SQL dans `authentication.py` | tests confidentialité, migration, retrait, navigateur admin |
| 15. User, Role, services d'accès | `users` et contraintes SQL représentent User/Role ; `ROLES`, `AuthenticationService`, `AuthorizationService` et API `web/security.py` | tests sécurité et navigateur |
| 16. Dashboard | `src/web/` : sélection patient, mesures, profils, courbes, alertes, état des connexions, plus console historique | trois scripts navigateur et tests API |

## Adaptations assumées

Les méthodes Python utilisent généralement `snake_case`. `ProgressiveStrategy`
et `SuddenChangeStrategy` réalisent les stratégies d'anomalies progressives et
brutales du diagramme. `RECOVERY` est un événement/une phase de récupération ;
il n'est pas ajouté à l'énumération UML des cinq états.

Node-RED est un flow exécutable et Mosquitto un conteneur : créer des classes
Python homonymes n'ajouterait pas leur comportement. L'abonnement MQTT existe
dans le flow et dans le récepteur Python. Les mots de passe MQTT sont hachés
côté broker ; un client conserve ses identifiants privés pour s'authentifier.
Les mots de passe applicatifs sont hachés avec Argon2id.

L'application combine les profils selon leurs règles sans diagnostic. Elle
utilise PostgreSQL et un dashboard JavaScript natif servi par FastAPI. React
était une option de stack, pas une exigence du diagramme.

## Réserves explicites

La couverture fonctionnelle du diagramme n'est pas une certification IEEE,
clinique ou réglementaire. Les métadonnées IEEE sont partiellement mappées ;
le chiffrement porte sur les charges de mesures/alertes, pas tous les index ou
les sauvegardes ; le consentement est enregistré par l'administrateur. Les
limites opérationnelles et la validation finale sont détaillées dans
[l'étape 12](step12_validation.md).
