# Étape 1 — Patients et profils cliniques

## Objectif

Représenter les patients surveillés et leur associer plusieurs profils cliniques.
P001 peut cumuler diabète et hypertension, tandis que P002 possède un profil de
suivi anxiété/stress. Les profils décrivent les priorités de surveillance ; ils
ne posent aucun diagnostic.

## Correspondance avec le diagramme UML

| Élément UML | Implémentation Python | Responsabilité |
| --- | --- | --- |
| `Patient` | `src/domain/patient.py` | Identité, activation, profils et paramètres |
| `ClinicalProfile` | `src/domain/clinical_profile.py` | Identifiant, nom, description, priorités et règles |
| `DiabetesProfile` | Même module | Priorités du profil diabète |
| `HypertensionProfile` | Même module | Priorités du profil hypertension |
| `AnxietyProfile` | Même module | Priorités du suivi anxiété/stress |
| `addProfile()` / `removeProfile()` | `add_profile()` / `remove_profile()` | Association et retrait |
| `priorityParameters` / `getRules()` | `priority_parameters` / `get_rules()` | Accès aux priorités et règles |

Les noms Python utilisent `snake_case`. L'héritage des trois profils spécialisés
et l'association d'un patient à plusieurs profils sont conservés.

## Patient

Le constructeur accepte `patient_id`, `name`, `monitoring_enabled=True` et
`profiles=None`. Un patient peut être créé sans profil pendant sa configuration.
L'ancienne liste `parameters` reste disponible : `add_parameter()` et
`remove_parameter()` gèrent les paramètres effectivement simulés.

`profiles` contient des objets `ClinicalProfile`, pas des chaînes de caractères.
`add_profile()` refuse un doublon ayant le même `profile_id`, même s'il s'agit
d'une autre instance. Il conserve alors le premier objet ; ce n'est pas une
opération de remplacement. `remove_profile()` compare également l'identifiant
et ne produit pas d'erreur si le profil est absent.

Chaque patient possède sa propre liste. Les objets profils transmis sont
référencés, pas copiés en profondeur : utiliser des instances distinctes si
leurs configurations doivent évoluer indépendamment entre patients.

## Profils disponibles

| Classe | `profile_id` | Paramètres prioritaires |
| --- | --- | --- |
| `DiabetesProfile` | `diabetes` | `glucose`, `activity`, `heart_rate` |
| `HypertensionProfile` | `hypertension` | `systolic_bp`, `diastolic_bp`, `heart_rate` |
| `AnxietyProfile` | `anxiety` | `heart_rate`, `hrv`, `respiratory_rate`, `activity` |

`get_priority_parameters()` calcule l'union ordonnée des priorités de tous les
profils. Un paramètre commun, comme `heart_rate`, apparaît une seule fois.

Ces priorités ne créent pas automatiquement des capteurs et n'interdisent pas
d'autres mesures. Ajouter un profil d'hypertension ne retire donc ni SpO₂ ni la
température de la liste des paramètres.

## Exemple

```python
from src.domain import Patient, DiabetesProfile, HypertensionProfile, AnxietyProfile

first = Patient("P001", "Patient 1")
first.add_profile(DiabetesProfile())
first.add_profile(HypertensionProfile())
first.add_profile(DiabetesProfile())
assert len(first.profiles) == 2

assert first.get_priority_parameters() == [
    "glucose", "activity", "heart_rate", "systolic_bp", "diastolic_bp",
]

second = Patient("P002", "Patient 2", profiles=[AnxietyProfile()])
first.remove_profile(DiabetesProfile())
second.monitoring_enabled = False
```

Depuis la racine du projet :

```sh
.venv/bin/python -m examples.step1_profiles
.venv/bin/python -m pytest -q tests/domain/test_patient.py tests/domain/test_clinical_profile.py
```

Les tests couvrent notamment le cumul de profils, les doublons, le retrait par
identifiant, l'indépendance des listes et la conservation des paramètres.

## Limites et raccordements

À l'étape 1, `monitoring_enabled` est un attribut de configuration. Depuis
[l'étape 3](step3_simulation.md), le simulateur le consulte à chaque lecture et
n'émet rien lorsqu'il vaut `False`.

`get_rules()` retourne une copie de la liste des règles. Depuis
[l'étape 6](step6_rules.md), les trois profils spécialisés possèdent des règles
de démonstration et le détecteur applique les profils aux mesures validées.
Le profil générique conserve une liste vide par défaut. L'affectation des
profils ne déclenche aucune alerte à elle seule.

La gestion des utilisateurs, des consentements et le stockage persistant des
patients restent prévus pour les étapes correspondantes du diagramme.
