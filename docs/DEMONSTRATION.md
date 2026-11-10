# Démonstration orale — 3 à 5 minutes

## Préparer avant le passage

Suivre l’installation du [README](../README.md), activer l’environnement Python et démarrer Docker.
Dans le premier terminal :

```sh
python smartcare.py start-demo --node-red
```

Se connecter à **https://127.0.0.1:8000/login**. Le premier utilisateur est `admin` avec le mot
de passe choisi dans `.env` privé ; les comptes déjà présents gardent leurs identifiants.
Ouvrir aussi **https://127.0.0.1:1880** et s’authentifier avec le compte éditeur `admin`, en lecture seule.
Sa première préparation utilise le mot de passe privé de démo ; les changements ultérieurs du compte
applicatif ne modifient pas celui de Node-RED. Préparer la confiance dans la CA locale avant le cours.

Les commandes suivantes s’exécutent dans un second terminal avec le même environnement activé.
Arrêter un scénario avec `Ctrl+C` avant le suivant. Ne pas lancer plusieurs simulateurs à la fois.

## 0:00–0:40 — Présenter le trajet

> « Smartcare est un prototype pédagogique. Nous simulons des capteurs, mais le trajet réseau est réel :
> Python publie en MQTT, Mosquitto distribue les messages, Node-RED valide leur format et Python applique
> les règles des profils. PostgreSQL conserve les historiques et l’API alimente le dashboard. »

Montrer le flow dans Node-RED, notamment l’entrée MQTT, le validateur et les sorties acceptée/rejetée.
Les règles de surveillance sont dans le backend Python, pas dans le dessin du flow.

## 0:40–1:30 — Mesures normales

```sh
python smartcare.py simulate normal
```

Sélectionner P001. Montrer ses profils diabète/hypertension, les cartes horodatées et la courbe.
Attendre environ 15 secondes : certaines règles ont besoin d’un historique avant de confirmer « Normal ».
Choisir P002 pour montrer que ses profils et priorités diffèrent.

> « Les mesures sont simulées et identifiées comme telles. Une même valeur n’a pas nécessairement
> la même règle de suivi pour tous les patients. »

## 1:30–2:15 — Anomalie réelle dans la chaîne

Arrêter le premier scénario avec `Ctrl+C`, puis :

```sh
python smartcare.py simulate anomaly
```

Revenir à P001. Avec les règles livrées, la glycémie simulée à 240 mg/dL déclenche une alerte.
Ouvrir Alertes pour voir le patient, le paramètre, le contexte, la gravité et l’heure.

> « Je change l’entrée du simulateur. Le message traverse toujours MQTT et Node-RED ; le moteur Python
> déclenche la règle. Il ne s’agit pas d’un diagnostic ni d’une alerte dessinée dans le navigateur. »

## 2:15–3:45 — Coupure puis récupération

Arrêter l’anomalie avec `Ctrl+C`, puis :

```sh
python smartcare.py simulate disconnection
```

P001 émet normalement pendant 15 secondes, se tait pendant 20 secondes avec la configuration livrée,
puis reprend. P002 et P003 continuent tout le temps. Montrer « Capteur déconnecté » et l’incident
technique distinct des alertes physiologiques. Attendre le retour des données ; le suivi peut rester
« À surveiller » le temps de reconstruire l’historique de tendance.

> « Le silence n’est jamais interprété comme un état normal. La reprise du capteur et la récupération
> physiologique sont deux choses différentes. »

## 3:45–4:30 — Accès et conclusion

Montrer brièvement Administration : comptes et rôles. Les consentements et l’audit sont repliés.
Expliquer qu’un médecin ou infirmier peut lire le suivi, mais ne peut pas administrer le système,
y compris en changeant manuellement l’URL.

> « Les sessions, rôles, consentements, TLS et le chiffrement des historiques restent actifs.
> Ce projet démontre une chaîne IoT ; les seuils ne sont pas validés pour soigner une personne. »

## Si rien n’apparaît

Vérifier que le simulateur n’a pas terminé ses 60 secondes, sélectionner P001 et cliquer sur Actualiser.
Vérifier « Réception active », puis le consentement dans Administration. Si nécessaire, ouvrir
« Détails techniques » et consulter les services :

```sh
docker compose -f compose.yaml -f compose.secure.yaml -f compose.demo.yaml ps
```

Une courbe vide après retrait du consentement est attendue. Une déconnexion après la fin du simulateur
est également attendue. Ne pas supprimer la base ou les clés pour tenter de réparer la démonstration.

À la fin : `Ctrl+C` dans les deux terminaux, puis `python smartcare.py stop`.
