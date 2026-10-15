# CLAUDE.md — Règles permanentes du projet FormationTunisie

> Lire ce fichier avant chaque nouvelle tâche et respecter ses règles.

## PROJET

Plateforme de gestion d’un centre de formation en Tunisie, développée avec
Django, Python, MySQL, HTML, CSS et Bootstrap.

## ENVIRONNEMENT TECHNIQUE

- Windows 10, PowerShell, Visual Studio Code.
- Python 3.11 dans l'environnement virtuel `.venv`.
- Django 5.2 (LTS). Le dossier de configuration du projet est `config/`.
- Base de données : MariaDB 11.4 (compatible MySQL) sur `127.0.0.1:3307`, base `formation_tunisie`,
  jeu de caractères `utf8mb4`. Administration via phpMyAdmin (XAMPP), serveur « MariaDB 11.4 (3307) ».
- Le MariaDB 10.4 de XAMPP (port 3306) contient d'autres bases sans rapport avec ce projet : ne pas y toucher.
- Les secrets et paramètres locaux sont dans `.env` (lu par `django-environ`, non versionné).
  `.env.example` sert de modèle.
- Langue `fr`, fuseau horaire `Africa/Tunis`.
- Dépôt Git : https://github.com/mohamedrachedheni/formation_tunisie (branche `main`).

Commandes courantes :

```powershell
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py test
python manage.py runserver
```

## OBJECTIFS

Le projet doit évoluer progressivement :

1. Site vitrine.
2. Catalogue de formations.
3. Gestion commerciale.
4. Gestion des candidats, inscriptions et sessions.
5. Espaces utilisateurs et administrateurs.

## RÈGLES DE DÉVELOPPEMENT

- Utiliser une architecture standard.
- Utiliser des noms de modèles et de champs cohérents, avec une convention unique dans tout le projet.
- Écrire des commentaires en français pour expliquer les règles métier importantes.
- Ne pas modifier la logique existante sans justification et sans signaler les changements.
- Avant chaque modification importante, examiner les fichiers concernés.
- Ne jamais écraser ou supprimer des données réelles.
- Ne jamais mettre de secrets dans le code.
- Utiliser les migrations Django pour modifier la structure de la base.
- Prévoir les contraintes d'intégrité, les index et les validations.
- Protéger les vues et les données par des permissions.
- Identifiants : conserver un `id` numérique (`BigAutoField`) comme clé primaire pour les relations SQL,
  et ajouter à chaque modèle métier un champ `uuid` (`UUIDField`, `default=uuid.uuid4`, unique, non modifiable)
  servant d'identifiant public.
- Ne jamais exposer l'`id` numérique dans les URL, vues, formulaires ou réponses : utiliser le champ `uuid`
  comme identifiant public (par exemple `to_field_name="uuid"` dans les `ModelChoiceField`).
  Exception : l'administration Django réservée au personnel.
- Le `uuid` ne remplace pas les contrôles d'accès : chaque vue vérifie les permissions.
- Écrire des tests pour chaque fonctionnalité métier importante.
- Exécuter les vérifications après chaque étape et corriger les erreurs avant de continuer.
- Ne pas prétendre qu'un test a réussi sans l'avoir réellement exécuté.
- Demander mon accord avant toute opération destructive, toute migration risquée, toute suppression
  ou tout changement d'architecture majeur.

## COMPTE RENDU DE FIN D'ÉTAPE

À la fin de chaque étape, fournir :

1. Les fichiers créés ou modifiés.
2. Les commandes à exécuter.
3. Les tests exécutés et leurs résultats.
4. Les éventuelles limites restantes.
5. La prochaine étape recommandée.
