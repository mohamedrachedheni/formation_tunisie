import uuid

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


class Roles:
    """Noms des groupes Django servant de rôles (seule source de vérité pour les rôles)."""

    ADMINISTRATEUR = 'Administrateur'
    GESTIONNAIRE = 'Gestionnaire'
    FORMATEUR = 'Formateur'
    CANDIDAT = 'Candidat'

    TOUS = (ADMINISTRATEUR, GESTIONNAIRE, FORMATEUR, CANDIDAT)


class UtilisateurManager(UserManager):
    def get_by_natural_key(self, username):
        # Connexion insensible à la casse de l'email (Ali@Exemple.tn = ali@exemple.tn).
        return self.get(**{f'{self.model.USERNAME_FIELD}__iexact': username})


class Utilisateur(AbstractUser):
    """Compte de connexion. L'email sert d'identifiant de connexion."""

    # Identifiant public (même principe que core.ModeleDeBase, dont ce modèle ne peut pas hériter
    # car il hérite déjà de AbstractUser).
    uuid = models.UUIDField('identifiant public', default=uuid.uuid4, unique=True, editable=False)
    email = models.EmailField('adresse email', unique=True)
    telephone = models.CharField('téléphone', max_length=20, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = UtilisateurManager()

    class Meta:
        verbose_name = 'utilisateur'
        verbose_name_plural = 'utilisateurs'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        # Les emails sont stockés en minuscules pour garantir l'unicité quelle que soit la saisie.
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    def a_le_role(self, role):
        return self.groups.filter(name=role).exists()
