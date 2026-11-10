# Workflows cliniques de l’interface

## Comptes professionnels

Un médecin ou un infirmier ouvre **Demander un compte** depuis la connexion. Le compte est
créé avec l’état `PENDING`, sans droit de connexion. L’administrateur le voit dans
**Administration → Utilisateurs** et clique sur **Valider le compte**. Cette action active le
compte, ferme toute ancienne session éventuelle et laisse une trace dans le journal d’accès.

## Patients

Un administrateur ou un médecin peut ajouter un patient depuis la surveillance. L’administrateur
dispose du même formulaire dans son écran de gestion. Un identifiant unique, un nom et au moins
un profil sont requis : diabète, hypertension ou suivi stress/anxiété. Le registre est conservé
dans PostgreSQL et rechargé au démarrage. Le consentement reste géré séparément ; sans accord,
les mesures sont masquées et la collecte est suspendue.

## Alertes

La page **Alertes** ouvre tout l’historique par défaut. Une alerte physiologique détectée reste
active même si les mesures reviennent à la normale : la récupération constitue un contexte, pas
une fermeture automatique. Admin, médecin ou infirmier peut cliquer sur **Résoudre l’alerte**.
Un infirmier peut aussi sélectionner un médecin actif et enregistrer **Contacter le médecin**.
Chaque action est horodatée, attribuée à son auteur et affichée dans l’historique de l’alerte.

## Audit

L’onglet **Audit** remplace les anciens détails techniques de la surveillance. Il présente l’état
des capteurs et une chronologie structurée des déconnexions, données manquantes, reprises et
changements d’état. Le journal administratif des connexions et modifications de comptes reste
réservé aux administrateurs.
