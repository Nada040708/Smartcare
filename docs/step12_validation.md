# Étape 12 — Validation finale et KPI

Cette étape clôt le prototype pédagogique décrit dans les 12 étapes. Elle vérifie
les scénarios, la chaîne réelle et les parcours utilisateur, puis complète les
deux éléments de confidentialité de l'UML : `Consent` et `EncryptionService`.
Le périmètre vérifié est celui du dépôt et du diagramme fourni. Le support
original de l'enseignante n'étant pas présent, sa conformité détaillée ne peut
pas être certifiée par cet audit.

## Résultats et preuves

Validation du 9 octobre 2026 : **387 cas pytest distincts réussis, aucun échec**.
Le profil sécurisé exécute 381 cas et le profil historique 379 ; leurs cas communs
sont dédupliqués. Les trois parcours Chromium ont réussi, sans erreur JavaScript,
sur ordinateur et mobile. Les contrôles de dépendances et des liens documentaires
locaux ont également réussi.

Le scénario KPI a stocké **163 / 163 mesures valides**, aucun doublon et aucun
des trois messages invalides. Sur cette exécution locale : acquisition/commit
**p95 = 89,78 ms**, API HTTPS **p95 = 20,8 ms**. Ce sont des résultats de cette
exécution, pas des garanties sur une autre machine.

Le serveur final a été redémarré sur **https://127.0.0.1:8000**, avec le schéma
`smartcare_dashboard_demo`. La migration a conservé 1 636 mesures et 30 alertes ;
un contrôle supplémentaire a transmis et relu 27 nouvelles mesures chiffrées.
Voir [la preuve de livraison](../reports/step12_delivery.json).

Ce schéma ne contient actuellement aucun compte utilisateur : le premier accès
nécessite de choisir le mot de passe administrateur avec la commande suivante.
Aucun mot de passe par défaut n'est installé.

```sh
.venv/bin/python -m src.security bootstrap --username admin --db-schema smartcare_dashboard_demo
```

Les résultats chiffrés de la dernière exécution sont dans
[le rapport KPI](../reports/step12_kpi.md) et [son JSON](../reports/step12_kpi.json).
Les suites produisent [pytest-secure.xml](../reports/pytest-secure.xml) et
[pytest-legacy.xml](../reports/pytest-legacy.xml). Le
[bilan des tests](../reports/step12_tests.md) compte les cas distincts : un même
test exécuté sous deux profils n'est pas compté deux fois.

Les deux profils sont testés successivement : les tests TLS exigent que les ports
1883/1880 soient fermés, alors que les anciennes démonstrations les utilisent.
Les exclusions propres à un profil sont donc normales ; leur union doit couvrir
tous les cas collectés. Un avertissement de dépréciation Starlette/TestClient
avec `httpx` est actuellement non bloquant et n'est pas masqué.

| Scénario / propriété | Vérification principale |
| --- | --- |
| Patients multiples, profils cumulés, séparation des historiques | `tests/domain/`, `tests/processing/test_profile_rules.py` |
| Normal, anomalie progressive et brutale | `tests/simulation/`, règles de seuil et de tendance |
| Combinaison stress avec activité au repos | `test_profile_rules.py` : présence, fraîcheur, décalage et contexte |
| Déclenchement, persistance, récupération, récidive | `test_monitoring_lifecycle.py`, `tests/storage/test_postgres.py` |
| Silence, reprise, paramètre absent, patient témoin | `test_connection_monitor.py`, `tests/storage/test_connections.py`, navigateur |
| Reconnexion MQTT / reprise après indisponibilité SQL | `tests/storage/test_tls_pipeline.py` ; défaillances injectées localement |
| JSON invalide, dates, unités, bornes, métadonnées | validateur Python, flow Node-RED, tests d'intégration |
| Doublons, transactions annulées, reprise durable | `tests/storage/test_postgres.py` |
| Sessions, rôles, CSRF, audit, dernier administrateur | `tests/storage/test_security.py`, navigateur |
| MQTT/TLS, certificats, authentification, ACL | `tests/storage/test_tls_pipeline.py` |
| Consentement absent, accordé, retiré, réaccordé | `tests/storage/test_privacy.py`, navigateur d'administration |
| Chiffrement, mauvaise clé, substitution, migration | `test_consent_encryption.py`, `tests/storage/test_privacy.py` |
| Recherche, courbes, filtres, pause, panne API, mobile | `scripts/check_final_browser.py` |

## Reproduire la validation

Prérequis : Docker Desktop, environnement `.venv`, Node.js pour les tests du
validateur JavaScript, certificats et clé privée générés selon le README.
Les tests SQL créent puis suppriment uniquement leurs schémas aléatoires.
Les scripts navigateur/KPI utilisent le port HTTPS 8443, qui doit être libre.
Ils créent des comptes temporaires à mot de passe aléatoire puis les suppriment.

```sh
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m src.security storage-key
docker compose -f compose.yaml -f compose.secure.yaml up -d --wait
.venv/bin/python -m pytest -q --postgres-integration --tls-integration --junitxml=reports/pytest-secure.xml
.venv/bin/python scripts/check_security_browser.py
.venv/bin/python scripts/check_final_browser.py
.venv/bin/python scripts/check_connections_browser.py
.venv/bin/python scripts/validate_step12.py
```

Pour les anciennes démonstrations, arrêter provisoirement le serveur applicatif
avant de changer de profil. Aucun volume ne doit être supprimé :

```sh
docker compose up -d --wait
.venv/bin/python -m pytest -q --postgres-integration --mqtt-integration --junitxml=reports/pytest-legacy.xml
# Restaurer le profil sécurisé, même si un test a échoué :
docker compose -f compose.yaml -f compose.secure.yaml up -d --wait
.venv/bin/python scripts/summarize_validation.py
.venv/bin/python -m src.web --db-schema smartcare_dashboard_demo
```

Les captures Chromium sont enregistrées sous `/tmp/smartcare-*.png`. Le client
HTTP vérifie réellement la CA et le nom du serveur ; seul le navigateur de test
éphémère accepte le certificat local sans ajout au trousseau de l'utilisateur.
Les [captures de cette livraison](../reports/screenshots/) conservent les vues
principales avec des données et des comptes de test fictifs.

## Définition des KPI

`scripts/validate_step12.py` utilise trois patients fictifs, neuf mesures scalaires
par cycle et six cycles, soit 162 observations pour les latences. Un dernier
message témoin porte le total à 163. Dix messages sont rejoués ; trois autres
sont volontairement invalides (valeur, unité, qualité). Le message témoin est
reçu après eux pour vérifier le résultat final stocké. Les identifiants patients
et le schéma sont isolés des données de démonstration.

| Indicateur | Calcul / cible locale fixée dans le script |
| --- | --- |
| Livraison | mesures uniques stockées / mesures valides uniques envoyées ; 100 % |
| Doublons stockés | nombre stocké − nombre valide unique envoyé ; 0 |
| Invalides stockés | recherche des trois identifiants invalides ; 0 |
| Acquisition → commit | horloge monotone avant publication jusqu'à la lecture d'une ligne SQL validée et déchiffrée ; p95 < 2 000 ms |
| API HTTPS | durée d'une requête authentifiée `/api/overview`, 25 échantillons ; p95 < 1 000 ms |
| Débit observé | mesures / durée du scénario séquentiel, pauses incluses ; descriptif uniquement |

Les percentiles utilisent le rang supérieur. La vérification SQL sonde toutes les
5 ms ; sa durée est incluse. Chaque cycle dure au moins 2,5 s pour laisser à la
règle de tendance sa fenêtre minimale de 10 s. Avant cela, `SURVEILLANCE` est
normal : des mesures dans les bornes ne suffisent pas à prouver une tendance
normale. Le passage à `NORMAL` des trois patients est vérifié.

Il s'agit d'une mesure locale à faible charge, sans engagement de performance.
Le rafraîchissement visuel toutes les trois secondes est distinct de la latence
du stockage. La précision clinique, la sensibilité et la spécificité ne sont
pas calculables à partir de ces données artificielles. Les tests vérifient les
règles configurées, pas leur validité médicale.

## Consentement

`Patient` peut porter un objet `Consent`. Par défaut, l'absence d'accord bloque
la collecte persistante et la consultation des valeurs. L'administrateur peut
enregistrer ou retirer l'accord dans **Administration → Consentements**.
Chaque décision est datée et auditée ; elle représente la saisie d'une décision,
pas une signature électronique ni une preuve juridique de consentement éclairé.

Les trois patients fictifs ont un `simulation_consent` explicite dans
`config/patients.json`. Une décision SQL prévaut toujours sur ce réglage, y compris
après redémarrage. Un nouveau patient n'hérite pas automatiquement de cet accord.

Le contrôle a lieu dans la transaction de collecte. Un verrou par patient
coordonne les écritures avec un retrait en cours. Après retrait, les nouvelles
mesures sont refusées, le suivi est suspendu, les valeurs/courbes/alertes sont
masquées et les API d'historique renvoient 403. L'identifiant et le nom restent
visibles pour permettre la gestion du patient. Une requête déjà autorisée avant
le retrait peut terminer ; la page ouverte se met à jour au prochain rafraîchissement.

Le retrait ne supprime pas les historiques. Un nouvel accord les rend à nouveau
consultables. Le simulateur peut continuer à émettre ses données fictives ; le
blocage est réalisé dans le backend, avant leur stockage.

## Chiffrement et migration 4

`EncryptionService` chiffre et authentifie les charges JSON de `measurements`
et `alerts` avec Fernet. Le contexte du schéma et de la table est inclus ;
l'identifiant du document est vérifié à la lecture. Les valeurs physiologiques
et les messages d'alerte ne sont plus lisibles directement dans ces charges SQL.
L'ancienne colonne `measurements.value`, redondante et en clair, est retirée.

La migration transforme les lignes existantes dans une seule transaction.
Elle exige l'arrêt de l'ancien écrivain de surveillance ; un verrou empêche de
migrer pendant sa collecte. Les migrations 1–4 sont ensuite enregistrées.
Une clé absente, erronée ou un jeton altéré provoque une erreur explicite,
sans repli vers un stockage non chiffré.

La clé `.secrets/storage.key` est générée avec des permissions 0600 et exclue de
Git. `python -m src.security storage-key` conserve une clé existante. L'installation
ne doit **jamais remplacer cette clé** pour réparer une erreur de lecture.
`SMARTCARE_STORAGE_KEY_FILE` permet d'indiquer une autre localisation. Sauvegarder
la clé séparément et de façon privée, avec une sauvegarde de la base : perdre la
clé rend les historiques irrécupérables. La rotation automatique n'est pas incluse.

Les identifiants, dates, paramètres, unités, qualités, sévérités/statuts et
index SQL restent en clair pour les requêtes. Les événements techniques,
connexions, comptes et audits ne sont pas chiffrés par ce service. Ce n'est
donc pas un chiffrement intégral de la base ou du disque. Les anciens exports,
sauvegardes et journaux WAL ne sont pas effacés rétroactivement. Une personne
contrôlant le compte système peut lire la clé et accéder aux données.

Référence du mécanisme utilisé : [documentation Fernet](https://cryptography.io/en/latest/fernet/).

## Périmètre terminé et limites

La chaîne de démonstration est complète : simulateurs → MQTT/TLS → Mosquitto →
Node-RED → validation et règles Python → PostgreSQL → dashboard HTTPS et alertes.
Le [tableau UML](uml_traceability.md) distingue les classes Python des composants
réalisés par un service externe ou par une table SQL.

Le dashboard utilise FastAPI et JavaScript natif, sans React. Les patients,
profils, règles et appareils se configurent dans `config/`, puis nécessitent un
redémarrage ; les comptes et consentements se gèrent dans l'interface.
Les alertes sont visibles dans le dashboard, sans SMS ni e-mail.

La nomenclature IEEE 11073 est **partielle**, avec codes non vérifiés explicitement
non mappés ; il n'y a pas de pile complète de communication IEEE ni de certification.
L'application ne pose aucun diagnostic. Le protocole de surveillance et ses
seuils sont des exemples pédagogiques. Une mise en service réelle nécessiterait
notamment validation clinique, gestion des accès par patient, durcissement et
exploitation adaptés, procédures de sauvegarde/restauration et étude du cadre
applicable. Le prototype ne revendique pas cette qualification.

Le récepteur est un écrivain unique par schéma. Les reconnexions sont testées,
mais aucune file durable locale ne garantit la récupération des mesures émises
pendant une coupure. PostgreSQL conserve sa configuration locale de laboratoire.
Ces limites sont explicites ; elles ne sont pas cachées derrière le succès des tests.
