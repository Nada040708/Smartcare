# Validation de la simplification — 10 novembre 2026

## Résultat actuel

**400 tests pytest distincts réussis, aucun échec et aucun cas laissé inexécuté** dans
l’union des deux profils. Les résultats d’octobre n’ont pas été réutilisés comme preuve.
Les tests ont utilisé le projet Docker `smartcare-validation`, des volumes distincts et des
schémas SQL temporaires. Aucun compte, historique, volume ou clé de l’installation existante
n’a été réinitialisé. Les nouveaux secrets de test ont été générés dans des dossiers temporaires.

| Exécution finale | Résultat |
| --- | --- |
| Profil sécurisé : `python -m pytest -q --postgres-integration --tls-integration --junitxml=reports/simplification-secure.xml` | 394 réussis, 6 exclus propres au profil historique |
| Profil historique : `python -m pytest -q --postgres-integration --mqtt-integration --junitxml=reports/simplification-legacy.xml` | 392 réussis, 8 exclus propres au profil TLS |
| `python scripts/check_security_browser.py` | Connexion/refus, comptes, consentement, activation, rôle, réinitialisation du mot de passe, refus admin pour infirmier, révocation et mobile : réussis |
| `python scripts/check_final_browser.py` | Vues Surveillance/Alertes, patients, courbe, périodes, filtre, clavier, pause, erreur API, mobile et déconnexion : réussis |
| `python scripts/check_connections_browser.py` | MQTT/TLS → Node-RED → SQL → UI, silence, patient témoin, reprise et paramètre manquant : réussis |
| `python scripts/check_demo_browser.py` | Setup neuf/conservateur, commandes CLI réelles, premier et second démarrages, normal/anomalie/coupure/reprise, valeurs anciennes et chiffrement : réussis |
| `python scripts/check_node_red_demo.py` | HTTPS local, lecture authentifiée du flow, refus anonyme et refus de déploiement, conservation du hash éditeur : réussis |
| `python -m pip check` | Aucune dépendance cassée |
| `node --check` sur les scripts modifiés, `git diff --check` | Aucun défaut signalé |

Les commandes Python ont été lancées avec `.venv/bin/python` sur cette machine macOS.
Docker Desktop a été démarré avec `open -a Docker`. Les services isolés ont été lancés avec
`docker compose -p smartcare-validation -f compose.yaml -f compose.secure.yaml up -d --wait`.
Le passage temporaire au profil historique s’est fait avec `docker compose -p smartcare-validation up -d --wait`,
puis le profil sécurisé a été rétabli dans un bloc de nettoyage. Le contrôle Node-RED a utilisé
`compose.demo.yaml` avec un fichier d’identifiants temporaire monté en lecture seule.

Le test CLI lance réellement `smartcare.py start-demo --project smartcare-validation --db-schema <schéma temporaire> --port 8445`
et `smartcare.py simulate normal`, `anomaly`, puis `disconnection`. Les autres tests navigateur
utilisent un serveur HTTPS temporaire sur 8443. Les seuls schémas supprimés à la fin sont ceux
créés par les tests. Les captures ont été examinées sur ordinateur et mobile.

Preuves : [XML sécurisé](../reports/simplification-secure.xml),
[XML historique](../reports/simplification-legacy.xml),
[comptage des cas distincts](../reports/simplification/tests.json),
[captures actuelles](../reports/simplification/).

## Corrections issues des vérifications

Le test des valeurs anciennes a été corrigé pour installer l’horloge contrôlée avant le
chargement du navigateur. Le sélecteur de compte pour réinitialiser un mot de passe dispose
maintenant d’un nom accessible explicite. Le contrôle Node-RED demande le scope du compte
lecture seule ; son middleware refuse les écritures avec HTTP 401. Le graphique est redessiné
au redimensionnement, même en pause. Les pages HTML privées ne sont plus accessibles via `/assets/`.
Un passage navigateur a dépassé son attente de connexion ; le contrôle attend désormais explicitement la réponse HTTP avant de vérifier la page. Ces points ont été corrigés et les contrôles concernés réexécutés avec succès.

## Fichiers modifiés ou ajoutés pour cette demande

| Ensemble | Fichiers |
| --- | --- |
| Lancement et initialisation | `smartcare.py`, `src/demo.py`, `src/security/demo.py`, `.env.example` |
| Mode Node-RED pédagogique | `compose.demo.yaml`, `infra/node-red/settings.demo.js`, `infra/node-red/start-secure.js` |
| API et état prudent en cas de perte MQTT | `src/web/app.py`, `src/web/queries.py` |
| Interface | `src/web/static/index.html`, `alerts.html`, `app.js`, `admin.html`, `login.html`, `style.css`, `security.css` |
| Nouveaux tests | `tests/test_demo.py`, `tests/storage/test_demo_bootstrap.py` |
| Parcours navigateur adaptés | `scripts/check_dashboard_browser.py`, `scripts/check_security_browser.py`, `scripts/check_connections_browser.py` |
| Nouveaux parcours de validation | `scripts/check_demo_browser.py`, `scripts/check_node_red_demo.py` |
| Documentation | `README.md`, `docs/COMPRENDRE_SMARTCARE.md`, `docs/DEMONSTRATION.md`, `docs/ARCHITECTURE_SIMPLE.md`, `docs/SECURITE_ET_TESTS.md`, `docs/VALIDATION_SIMPLIFICATION.md` |
| Preuves produites | `reports/simplification-secure.xml`, `reports/simplification-legacy.xml`, `reports/simplification/tests.json`, `reports/simplification/changed-files.json`, captures dans `reports/simplification/` |

Le [manifeste](../reports/simplification/changed-files.json) donne les chemins complets et les
empreintes des sources/documentations de cette modification. Le dépôt comportait déjà de
nombreuses modifications non commitées : elles ont été conservées. Le moteur de règles,
les migrations, le chiffrement, les ACL et le service d’authentification existants sont réutilisés.

## Limites de cette vérification

Un avertissement non bloquant de Starlette signale la dépréciation de son client de test `httpx`.
Windows/Linux sont documentés mais n’ont pas été exécutés ici. L’éditeur Node-RED a été vérifié
via HTTPS et son API authentifiée ; les parcours Chromium couvrent le dashboard et l’administration.
Aucun nouveau benchmark de charge ni chiffre de précision médicale n’est revendiqué.
Le renouvellement automatique des certificats n’est pas implémenté. Les limites pédagogiques,
IEEE, de récupération des messages et d’exploitation sont conservées dans
[la documentation avancée](SECURITE_ET_TESTS.md).
