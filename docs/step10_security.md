# Étape 10 — Authentification, rôles, audit et TLS

## Résultat

Le dashboard exige maintenant une connexion, et chaque route qui retourne des
données vérifie la session côté serveur. L'administrateur dispose d'une page
de gestion des comptes. MQTT fonctionne avec TLS, authentification et
permissions de topics dans le profil Docker sécurisé. Le dashboard utilise HTTPS.

Cette étape conserve les règles, mesures et alertes des étapes précédentes.
Elle ne modifie pas leur interprétation clinique. Les données restent simulées.

```text
Simulateur ── MQTT/TLS + compte simulator ──► Mosquitto :8883
                                                  ↕ MQTT/TLS + compte node-red
                                              Node-RED
                                                  ↓ reçus validés via Mosquitto
                        MonitoringReceiver (compte receiver, TLS)
                                                  ↓
                                Moteur de règles → PostgreSQL
                                                       ↑
Navigateur ── HTTPS :8000 ──► session → autorisation → API
                                      ↓
                              journal des accès
```

## Installation et premier lancement

Utiliser Python dans `.venv`, Docker Desktop démarré et Docker Compose **2.24.4
ou plus récent** (la configuration emploie `!override` pour remplacer les ports).
Exécuter les commandes depuis la racine du projet.

### 1. Dépendances et secrets locaux

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/setup_security.py
```

Le script crée `.secrets/` avec des permissions privées, une autorité de
certification locale, des certificats distincts pour le broker et le dashboard,
ainsi que quatre mots de passe MQTT aléatoires. Le fichier du broker contient
les hachages produits par `mosquitto_passwd`, exécuté dans un conteneur éphémère.
Aucun mot de passe n'est affiché ni ajouté au dépôt.

**Cette préparation se fait une seule fois.** Si `.secrets/` existe déjà, le
script refuse de remplacer son contenu. Après la réalisation de cette étape
dans l'espace de travail, les fichiers y sont déjà présents : passer à la suite.
`.secrets/` et `.env` sont ignorés par Git. Les clients MQTT ont nécessairement
leur secret de connexion dans leur fichier privé ; seuls les hachages sont
utilisés par le broker pour vérifier les mots de passe.

### 2. Services sécurisés

```sh
docker compose -f compose.yaml -f compose.secure.yaml up -d --wait
```

Le même projet Compose conserve les volumes PostgreSQL et Node-RED. Le broker
écoute sur `127.0.0.1:8883`. Les anciens ports **1883 et 1880 ne sont plus
exposés**. Dans ce mode, Node-RED est un orchestrateur sans éditeur ni API
d'administration (`httpAdminRoot: false`). Il charge le flow versionné, ajoute
la configuration TLS et désactive les nœuds de debug affichant les mesures.
Le flow modifié depuis l'ancien éditeur reste conservé dans son volume ; le
profil sécurisé utilise le flow versionné, pas ces éventuelles modifications.

Ne pas relancer ensuite `docker compose up` seul : cela réactiverait la
configuration pédagogique non chiffrée des anciennes étapes. Toujours fournir
les deux fichiers pour le fonctionnement sécurisé.

### 3. Créer le premier administrateur

```sh
.venv/bin/python -m src.security bootstrap --username admin --db-schema smartcare_dashboard_demo
```

Saisir et confirmer un mot de passe de **12 à 128 caractères**. La saisie est
masquée et aucun mot de passe par défaut n'est fourni. Cette commande applique
les migrations puis crée le premier compte uniquement si aucun compte n'existe.
Pour une installation neuve utilisant le schéma standard `smartcare`, omettre
`--db-schema` dans cette commande **et** dans le lancement du serveur.

Les comptes sont propres au schéma PostgreSQL : utiliser le même schéma pour
le bootstrap et le dashboard. Les comptes de test automatique sont créés dans
des schémas temporaires et supprimés après les tests ; ils ne servent pas à la
connexion de l'utilisateur du projet.

### 4. Dashboard HTTPS

Arrêter l'ancien serveur HTTP avec `Ctrl+C` s'il occupe encore le port 8000.

```sh
.venv/bin/python -m src.web --db-schema smartcare_dashboard_demo
```

Ouvrir **https://127.0.0.1:8000**, puis se connecter avec le compte créé.
Le serveur ne se lie qu'à `127.0.0.1`, avec un seul worker. Le récepteur utilise
par défaut `.secrets/receiver.json` et le port MQTT 8883. Lancer un seul moteur
de surveillance par schéma, comme à l'étape 9.

Le certificat est signé par une **CA locale de développement**, pas par une
autorité publique : le navigateur ne lui fait pas confiance automatiquement.
Pour cette démonstration, importer `.secrets/tls/ca.crt` dans le magasin de
certificats de confiance du navigateur/système utilisé. Sur macOS, cela peut se
faire avec Trousseaux d'accès dans le trousseau de session ; vérifier le nom
« Smartcare local development CA » et n'importer que le certificat `.crt`.
La clé `ca.key` doit rester privée. Retirer cette confiance après la démonstration.
Le projet ne modifie pas automatiquement le trousseau du système.

Une vérification en ligne de commande ne nécessite pas de modifier le trousseau :

```sh
curl --cacert .secrets/tls/ca.crt https://127.0.0.1:8000/api/overview
# Sans session : {"detail":"Connexion requise."}, statut HTTP 401.
```

Options disponibles : `--tls-cert`, `--tls-key`, `--mqtt-config`, `--mqtt-port`,
`--broker`, `--port`, `--patients`, `--no-ingest` et `--db-schema`.
Un certificat manquant provoque une erreur ; le lancement normal ne revient
pas silencieusement à HTTP. `--no-ingest` permet une consultation HTTPS des
historiques sans connexion MQTT.

### 5. Données en direct

Dans un autre terminal :

```sh
.venv/bin/python -m examples.step9_live --port 8883 --mqtt-config .secrets/simulator.json
```

Le simulateur conserve les scénarios de l'étape 9. La chaîne MQTT → Node-RED →
Python → PostgreSQL reste identique, avec des connexions MQTT chiffrées.

## Utilisation et permissions

| Action | ADMIN | DOCTOR | NURSE |
| --- | --- | --- | --- |
| Patients, dernières mesures, courbes, alertes, événements | Oui | Oui | Oui |
| Créer un compte | Oui | Non | Non |
| Modifier un rôle, activer/désactiver un compte | Oui | Non | Non |
| Réinitialiser un mot de passe | Oui | Non | Non |
| Consulter le journal d'audit | Oui | Non | Non |

Le lien **Administration** apparaît uniquement pour l'administrateur. La page
permet de créer les comptes médecin/infirmier, modifier les rôles, désactiver
ou réactiver un compte et réinitialiser son mot de passe. Le dernier
administrateur actif ne peut pas être désactivé ou rétrogradé, même en cas de
requêtes concurrentes. Les changements révoquent toutes les sessions du compte
concerné ; modifier son propre compte oblige donc à se reconnecter.

Les trois rôles partagent actuellement la même liste de patients. L'affectation
individuelle d'un patient à un soignant n'est pas implémentée. Médecin et
infirmier ont les mêmes droits de consultation, car le prototype ne propose
pas encore d'actes cliniques réservés à l'un de ces rôles.

La gestion des profils reste dans `config/patients.json`. Les alertes restent
résolues par le moteur ; aucune résolution manuelle n'est ajoutée ici.

## Authentification et sessions

- Mots de passe hachés en **Argon2id**, avec sel aléatoire, 64 Mio de mémoire,
  trois itérations et parallélisme 2. Les API ne retournent jamais le hachage.
- Jeton de session opaque aléatoire de 256 bits. PostgreSQL ne stocke que son
  SHA-256. Aucun jeton n'est stocké dans `localStorage`.
- Cookie `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/`, sans domaine partagé.
- Durée absolue maximale de huit heures et expiration après trente minutes
  sans requête authentifiée. Le rafraîchissement du dashboard compte comme
  activité : laisser un écran ouvert conserve la session jusqu'à sa limite
  absolue. Une pause peut toujours provoquer une expiration après inactivité.
- Nouvelle session à chaque connexion ; l'ancienne session du navigateur est
  révoquée. La déconnexion révoque le jeton côté serveur et efface le cookie.
- Protection des écritures par contrôle strict de l'origine et jeton CSRF.
  Le login vérifie aussi l'origine. Les requêtes GET ne changent ni mesure,
  ni alerte, ni compte ; elles peuvent actualiser l'activité de la session.
- Dix échecs par identifiant ou cinquante par adresse réseau dans une fenêtre
  de cinq minutes entraînent HTTP 429. Les compteurs sont persistants, partagés
  dans le schéma, et sérialisés en transaction. Les adresses sont représentées
  par une empreinte pour le compteur, pas conservées en clair dans l'audit.
- Identifiant inexistant, compte désactivé et mot de passe erroné renvoient le
  même message. Les erreurs de validation n'incluent pas le contenu saisi.
- Contrôle du rôle dans le backend, même pour un appel API direct. Une
  révocation ou une modification du rôle est prise en compte dès la prochaine
  requête. Les mutations relisent également l'administrateur en transaction.

Les pages et réponses utilisent `Cache-Control: no-store`, une politique CSP,
`X-Content-Type-Options` et `Referrer-Policy`. Les en-têtes de proxy ne sont pas
acceptés par le lanceur local. Les hôtes autorisés sont limités aux hôtes locaux
(et `testserver` pour les tests). Les pages Swagger/OpenAPI publiques sont
désactivées ; les contrats utiles sont documentés ci-dessous.

## TLS et comptes MQTT

Les clients vérifient la chaîne du certificat **et** le nom du serveur. TLS 1.2
est le minimum ; la négociation peut utiliser TLS 1.3. Il n'y a ni désactivation
de la vérification ni repli en clair. L'authentification MQTT utilise un mot de
passe dans le canal TLS ; le prototype n'impose pas de certificat client mTLS.

| Compte technique | Lecture | Écriture |
| --- | --- | --- |
| `simulator` | Aucune | `health/+/vitals` |
| `node-red` | `health/+/vitals` | `health/+/received`, `health/+/rejected` |
| `receiver` | `health/+/received` | Aucune |
| `healthcheck` | Aucune | `smartcare/healthcheck` |

Tout autre accès est refusé par défaut. Le simulateur multipatient est un seul
acteur technique de démonstration ; des appareils réels nécessiteraient des
identifiants et permissions par appareil/patient.

Les fichiers clients privés sont des JSON `{ca_file, username, password}`.
Le chemin `ca_file` est relatif au fichier JSON. `TLSService` configure un
contexte SSL vérifié et `MQTTAuthentication` porte les identifiants. Leur
représentation Python n'affiche pas le mot de passe. Un mot de passe n'est
jamais fourni sur la ligne de commande des programmes Python.

Le broker copie ses hachages et sa clé dans un `tmpfs` avec propriétaire
Mosquitto et permissions 0600. Node-RED prépare ses credentials dans un autre
`tmpfs` privé (UID 1000, répertoire 0700, fichiers 0600), sans éditeur et sans
persistance de ces credentials. Les sources restent montées en lecture seule.
Certains fichiers destinés aux conteneurs sont lisibles par leur UID dans le
montage ; le répertoire hôte `.secrets` est protégé par le mode 0700.
La clé de la CA n'est montée dans aucun service.

Les certificats serveur expirent après 90 jours, la CA après 365 jours. Pour
les renouveler dans ce prototype, arrêter le dashboard et les services MQTT,
archiver `.secrets/` dans un emplacement privé, relancer le script de préparation,
puis recréer Mosquitto et Node-RED avec le profil sécurisé. Cela renouvelle aussi
les comptes MQTT ; les comptes applicatifs PostgreSQL sont conservés. Importer
la nouvelle CA et retirer l'ancienne confiance. Aucun renouvellement automatique
ou gestionnaire de secrets de production n'est livré ici.

## Stockage et audit

La migration `002_security.sql` ajoute `users`, `auth_sessions`, `auth_throttle`
et `audit_logs`. Elle s'applique automatiquement après la migration 1, sous
verrou, sans effacer les mesures, les alertes ni les événements existants.

Le journal conserve : premier administrateur, connexions réussies/refusées,
limitation des tentatives, déconnexions, créations/modifications de comptes et
refus d'autorisation/CSRF. Il contient la date UTC, le compte lorsqu'il est
connu, l'action et l'identifiant du compte visé. Il n'enregistre ni mots de
passe, ni cookies, ni valeurs physiologiques. Le polling des mesures n'est pas
audité à chaque requête. La consultation est réservée à l'administrateur et
paginée. Aucune API ne modifie ou n'efface ce journal ; il n'est cependant pas
inviolable pour l'administrateur de la base.

## API de sécurité

| Route | Utilisation |
| --- | --- |
| `POST /api/auth/login` | JSON `username`, `password` ; origine obligatoire ; retourne utilisateur et jeton CSRF, définit le cookie |
| `GET /api/auth/me` | Session courante et jeton CSRF |
| `POST /api/auth/logout` | Session, origine et en-tête `X-CSRF-Token` |
| `GET /api/admin/users` | Liste sans mots de passe ni hachages |
| `POST /api/admin/users` | JSON `username`, `password`, `role` ; administrateur + CSRF |
| `PATCH /api/admin/users/{user_id}` | Une ou plusieurs clés : `role`, `active` booléen, `password` ; administrateur + CSRF |
| `GET /api/admin/audit?limit=50&offset=0` | Audit administrateur ; limite maximale 100 |

Les quatre API de données de l'étape 9 nécessitent une session valide. Codes
principaux : 401 connexion requise/expirée, 403 accès refusé, 409 conflit,
422 saisie invalide, 429 limitation, 503 stockage indisponible. Une indisponibilité
de la base ne donne jamais accès aux données sans authentification.

## Fichiers et correspondance UML

| Élément | Implémentation |
| --- | --- |
| User / Role | Table `users`, rôles validés et représentations publiques sans hachage |
| AuthenticationService | `src/security/authentication.py` : login, vérification, logout et comptes |
| AuthorizationService / AuditLog | Même module : permissions et journal PostgreSQL |
| TLSService / MQTTAuthentication | `src/communication/tls.py` |
| Contrôles HTTP | `src/web/security.py`, intégration dans `app.py` |
| Bootstrap administrateur | `python -m src.security bootstrap` |
| Interface | `login.html`, `admin.html`, scripts associés et intégration au dashboard |
| Certificats / secrets | `scripts/setup_security.py`, sortie privée `.secrets/` |
| Broker / Node-RED | `compose.secure.yaml`, configuration et scripts `infra/` |

## Vérification reproductible

Avec le profil sécurisé démarré :

```sh
.venv/bin/python -m pytest -q --postgres-integration --tls-integration
```

Cette commande teste la protection des API, les trois rôles, Argon2id, les
cookies, CSRF, expiration/révocation, audit, limitation, comptes concurrents,
TLS, les certificats invalides, les ACL et le trajet réel jusqu'à PostgreSQL.
Les tests MQTT historiques sur le port 1883 sont volontairement ignorés dans
ce profil. Ne pas combiner `--mqtt-integration` et `--tls-integration`.

Pour revérifier les anciennes étapes séparément, arrêter le serveur sécurisé,
revenir temporairement au Compose de base, exécuter les tests, puis réactiver TLS :

```sh
docker compose up -d --wait
.venv/bin/python -m pytest -q --postgres-integration --mqtt-integration
docker compose -f compose.yaml -f compose.secure.yaml up -d --wait
```

Test navigateur autonome, sans utiliser votre compte ni vos données :

```sh
.venv/bin/python -m pip install -r requirements-browser.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/check_security_browser.py
```

Il crée un schéma PostgreSQL unique, deux comptes fictifs et un serveur HTTPS
temporaire sur 8443, puis les supprime à la fin. Le port 8443 doit être libre.
Il vérifie connexion, erreurs, création/activation de compte, rôles, audit,
déconnexion, révocation et affichage mobile. Les captures sont dans
`/tmp/smartcare-login-{desktop,mobile}.png` et
`/tmp/smartcare-admin-{desktop,mobile}.png`.

Le client HTTP de ce test vérifie réellement la CA et le nom du serveur.
Le navigateur de test éphémère accepte ensuite cette CA locale via une exception
de test ; cela ne change ni le trousseau personnel ni les clients MQTT.

## Limites et suite

Cette étape protège le transport MQTT et web ainsi que l'accès applicatif.
La connexion PostgreSQL reste celle du laboratoire local (port 5433 lié à
loopback, réseau Docker). Son mot de passe de démonstration, le chiffrement
des volumes/sauvegardes et le TLS PostgreSQL ne sont pas durcis ici. Une personne
ayant accès au compte système ou à la base peut contourner les rôles de l'API.

Les classes UML `EncryptionService` et `Consent` sont désormais implémentées à
[l'étape 12](step12_validation.md), avec migration des données et tests de retrait
du consentement. MFA, récupération autonome de mot de passe, sessions
distribuées à grande échelle, rétention de l'audit et affectation soignant/patient
restent hors de ce prototype. Les comptes sont administrés localement ; si tous
les mots de passe administrateur sont perdus, une procédure opérateur distincte
sera nécessaire (le bootstrap refuse d'écraser un compte existant).

L'option explicite `--allow-insecure-local` du lanceur web conserve HTTP et le
port 1883 pour reproduire les anciennes démonstrations. L'authentification reste
obligatoire, mais le cookie n'a alors pas l'attribut Secure. Ce mode n'est pas
le lancement normal de l'étape 10.

La gestion des pannes est maintenant décrite dans [l'étape 11](step11_connections.md).
La validation finale et les limites du prototype sont décrites dans
[l'étape 12](step12_validation.md) et la [traçabilité UML](uml_traceability.md).

Références : [sessions OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[stockage des mots de passe](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html),
[Mosquitto](https://mosquitto.org/man/mosquitto-conf-5.html),
[Paho MQTT](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html),
[sécurisation Node-RED](https://nodered.org/docs/user-guide/runtime/securing-node-red).
