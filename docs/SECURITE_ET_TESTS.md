# Sécurité, exploitation locale et tests

## Deux modes explicites, mêmes garanties de transport

`python smartcare.py start-demo` active explicitement la démonstration locale. Il prépare
les services et peut créer le premier `admin`, uniquement si la table des comptes est vide.
Le mot de passe vient de `SMARTCARE_DEMO_ADMIN_PASSWORD` ou d’une saisie masquée enregistrée
dans `.env`. Aucun mot de passe fixe ne figure dans le dépôt ou dans la page de connexion.
Un compte existant prévaut sur la variable : le démarrage ne le réinitialise jamais.
L’initialisation concurrente utilise le verrou déjà présent dans le bootstrap.

Le mode sécurisé normal garde le bootstrap manuel, sans initialisation automatique :

```sh
# Première installation uniquement, si .secrets n’existe pas :
python scripts/setup_security.py
docker compose -f compose.yaml -f compose.secure.yaml up -d --wait
# Seulement si aucun compte n’existe :
python -m src.security bootstrap --username admin
python -m src.web
```

Le schéma par défaut est `smartcare` dans les deux chemins. Pour retrouver une ancienne
installation, utiliser le même `--db-schema` que précédemment, par exemple celui indiqué
dans les anciens documents. La commande n’effectue aucun transfert ou effacement de schéma.
Les options `--port` et `--project` du lanceur servent aux conflits de ports et aux tests ;
elle ne change pas les ports MQTT/PostgreSQL configurés.

`--node-red` ajoute `compose.demo.yaml` aux deux fichiers Compose précédents. Il expose
l’éditeur **en HTTPS sur 127.0.0.1:1880 uniquement**, avec authentification bcrypt et permission
`read`. Aucune permission anonyme n’est configurée. Son mot de passe initial est celui de la
première préparation, conservé sous forme de hash dans `.secrets/editor.json`. Ce compte
est indépendant du compte applicatif. Les déploiements et modifications du flow sont refusés.
Le profil sécurisé sans cet ajout garde `httpAdminRoot: false` et aucun port publié.
Référence : [authentification et permissions Node-RED](https://nodered.org/docs/user-guide/runtime/securing-node-red).

## Protections conservées

Les mots de passe applicatifs utilisent Argon2id ; les sessions serveur sont expirables et
révocables, avec cookies HttpOnly/Secure/SameSite et contrôle CSRF/origine sur les mutations.
Les rôles sont vérifiés dans les endpoints, indépendamment de la visibilité des liens.
Le dernier administrateur ne peut pas être désactivé ou rétrogradé. Les pages HTML privées
ne sont pas servies par le répertoire public des assets.

Le consentement absent ou retiré bloque la collecte persistante et masque les données de suivi.
Un consentement enregistré en base prévaut sur celui, fictif, de `config/patients.json`.
Le retrait conserve les historiques. Les sections Consentements et Audit sont repliées dans
l’administration, mais leurs fonctions et contrôles serveur sont conservés.

Les charges des mesures et alertes sont chiffrées et authentifiées avec Fernet. Les identifiants,
index et certaines métadonnées techniques restent en clair : ce n’est pas un chiffrement intégral
du disque. MQTT conserve authentification, TLS et ACL. PostgreSQL reste une base locale de
laboratoire ; son mot de passe d’exemple et son transport local ne constituent pas un déploiement
hospitalier durci. Aucun élargissement des droits d’accès réseau n’est effectué par la démo.

## Certificats locaux

La première préparation crée une CA locale et des certificats serveur. Le navigateur ne connaît
pas cette CA automatiquement. Importer **uniquement** `.secrets/tls/ca.crt`, généré pour ce dépôt :

- macOS : ouvrir le certificat dans Trousseaux d’accès, l’ajouter au trousseau choisi et régler
  sa confiance pour SSL. Retirer cette confiance après la démonstration si elle n’est plus utile.
- Windows : importer le certificat pour l’utilisateur courant dans les autorités racines de confiance
  avec le gestionnaire de certificats. Utiliser uniquement un poste personnel/de laboratoire autorisé.
- Linux : utiliser le gestionnaire de certificats du navigateur ou le mécanisme de confiance propre
  à la distribution. Firefox peut utiliser son propre magasin de certificats.

Ne jamais distribuer `ca.key`, `web.key`, `broker.key` ni la clé de stockage. Aucun script ne modifie
le trousseau de l’utilisateur. Les clients MQTT vérifient la CA et le nom du serveur.

Les certificats serveur générés sont valables 90 jours, la CA 365 jours. Le nouveau lanceur refuse
un certificat expiré. Vérifier d’abord l’horloge système ; le renouvellement doit réémettre les
certificats serveur avec la CA existante ou suivre une rotation planifiée. **Le renouvellement
automatique n’est pas implémenté.** Ne jamais effacer `.secrets` pour réparer cette erreur :
ce dossier contient aussi la clé irremplaçable des historiques.

## Secrets, sauvegarde et données existantes

`.env` et `.secrets/` sont ignorés par Git. La saisie interactive conserve le mot de passe de démo
dans `.env`, avec permissions 0600 sur les systèmes POSIX ; les fichiers montés dans Node-RED
restent dans le dossier privé `.secrets`. Sous Windows, protéger ce dossier avec les permissions
du compte utilisateur. Ne pas inclure ces fichiers dans une capture ou une archive à remettre.

Conserver une sauvegarde privée des clés séparément d’une sauvegarde PostgreSQL. Sans
`.secrets/storage.key`, les mesures chiffrées sont irrécupérables. La préparation conserve les
secrets existants ; si le dossier est incomplet, elle refuse de le reconstruire silencieusement.
Elle ne réinitialise ni les données, ni les volumes, ni les comptes. En cas de perte du mot de
passe d’un compte existant, utiliser un autre administrateur autorisé ; le bootstrap ne remplace
pas le compte perdu. La récupération autonome n’est pas incluse.

## Inventaire réutilisé

La simplification réutilise les dépendances existantes : Paho MQTT, psycopg, FastAPI/Uvicorn,
Argon2, cryptography, python-dotenv, pytest et Playwright facultatif. Aucun framework frontend
ni service supplémentaire n’est introduit.

Les API de suivi restent `/api/overview`, `/api/patients/{id}/history`, `/api/alerts` et
`/api/patients/{id}/events`. Les API `/api/auth/*` et `/api/admin/*` conservent leurs protections.
La nouvelle route HTML `/alerts` réutilise `/api/alerts`. Il n’y a aucune API permettant au
navigateur de lancer des processus de simulation. Les profils, règles, alertes, états,
transactions, déduplication et le dessin SVG des courbes ont été réutilisés.

## Vérifications reproductibles, séparées de la démonstration

Les tests unitaires n’exigent pas Docker :

```sh
python -m pytest -q
```

Les tests d’intégration créent des schémas aléatoires, puis ne suppriment que ceux-ci.
Pour éviter toute écriture dans les volumes de l’application, arrêter son serveur et ses
conteneurs, puis utiliser un projet Compose **distinct**. Les ports étant identiques,
les deux piles ne doivent pas fonctionner simultanément :

```sh
docker compose -p smartcare-validation -f compose.yaml -f compose.secure.yaml up -d --wait
python -m pytest -q --postgres-integration --tls-integration --junitxml=reports/simplification-secure.xml
```

Si un `DATABASE_URL` privé pointe vers une autre base, ne pas exécuter ces tests avant de
l’avoir remplacé, dans l’environnement de test, par la connexion à la base isolée.
Node.js est requis pour vérifier aussi le validateur JavaScript local.
Les tests navigateur nécessitent Chromium et des ports libres 8443/8445 :

```sh
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
python scripts/check_security_browser.py
python scripts/check_final_browser.py
python scripts/check_connections_browser.py
python scripts/check_demo_browser.py
python scripts/check_node_red_demo.py
```

Les deux derniers scripts utilisent explicitement `smartcare-validation`. Ils génèrent des
secrets/comptes temporaires ; ils ne changent pas les clés de l’application. Le contrôle de l’éditeur
restaure le profil sécurisé à sa sortie. Le certificat local est accepté dans le navigateur de test
éphémère ; les clients HTTP/MQTT vérifient réellement la CA et le nom du serveur.
Le test des valeurs anciennes avance uniquement l’horloge du navigateur de test.

Les six anciens tests MQTT utilisent leur profil historique, toujours dans la pile isolée :

```sh
docker compose -p smartcare-validation up -d --wait
python -m pytest -q --postgres-integration --mqtt-integration --junitxml=reports/simplification-legacy.xml
# Restaurer le profil sécurisé même si un test échoue :
docker compose -p smartcare-validation -f compose.yaml -f compose.secure.yaml up -d --wait
# Après les vérifications :
docker compose -p smartcare-validation -f compose.yaml -f compose.secure.yaml stop
```

Aucun `down -v` n’est nécessaire. Les volumes de test ont le préfixe `smartcare-validation_`.
Les anciens rapports d’octobre sont des archives ; les résultats actuels figurent dans
[la validation de la simplification](VALIDATION_SIMPLIFICATION.md).

## Limites du prototype

Les seuils sont pédagogiques, la nomenclature IEEE 11073 partielle, et aucun diagnostic n’est
produit. Les messages émis pendant une coupure ne sont pas garantis récupérables : pas de file
durable de retransmission. Le navigateur s’actualise toutes les trois secondes ; la mesure peut
donc être stockée avant d’être visible. L’état reste « À surveiller » si les éléments nécessaires
à un suivi normal manquent. Les historiques techniques affichés sont volontairement bornés.

Le chemin Windows/Linux est documenté et les commandes utilisent Python et Compose ; leur
exécution doit être distinguée des tests réellement effectués sur macOS. Les contrôles ne
constituent ni une certification clinique, ni une preuve d’absence de toute vulnérabilité.
