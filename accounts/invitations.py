"""Création des accès aux espaces (candidat, formateur) par le centre.

Seules les personnes connues du centre reçoivent un compte : le Gestionnaire lance l'action
« Créer ou renouveler l'accès » sur une fiche ; un lien d'activation personnel, à usage unique et
valable 7 jours, est généré et transmis par WhatsApp ou par email. La personne y choisit son mot de passe.
"""

import re
from dataclasses import dataclass
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.urls import reverse

from core.validators import telephone_international

from .jetons import encoder_identifiant, generateur_invitation


@dataclass
class ResultatInvitation:
    personne: str
    lien: str = ''
    lien_whatsapp: str = ''
    message: str = ''
    erreur: str = ''


def _nom_utilisateur_disponible(email):
    Utilisateur = get_user_model()
    base = re.sub(r'[^a-z0-9._-]', '', email.split('@')[0].lower())[:120] or 'utilisateur'
    nom, numero = base, 2
    while Utilisateur.objects.filter(username=nom).exists():
        nom, numero = f'{base}{numero}', numero + 1
    return nom


def lien_activation(request, utilisateur):
    chemin = reverse('accounts:activation', kwargs={
        'uidb64': encoder_identifiant(utilisateur),
        'token': generateur_invitation.make_token(utilisateur),
    })
    return request.build_absolute_uri(chemin)


def inviter(request, fiche, role, nom_centre=''):
    """Crée (ou retrouve) le compte de la fiche (Candidat ou Formateur), le rattache et prépare le lien d'activation.

    `fiche` doit avoir les attributs prenom, nom, email, telephone et utilisateur.
    Règles :
    - un email est indispensable (c'est l'identifiant de connexion) ;
    - un compte déjà activé n'a pas besoin d'invitation (la personne utilise « mot de passe oublié ») ;
    - un compte existant avec le même email est réutilisé, sauf s'il est déjà rattaché à une autre fiche du même type.
    """
    Utilisateur = get_user_model()
    personne = f'{fiche.prenom} {fiche.nom}'
    email = (fiche.email or '').strip().lower()
    if not email:
        return ResultatInvitation(personne, erreur='Aucun email sur la fiche : ajoutez-en un (il servira d’identifiant de connexion).')

    with transaction.atomic():
        utilisateur = fiche.utilisateur or Utilisateur.objects.filter(email__iexact=email).first()
        if utilisateur is not None:
            # Un compte ne peut être rattaché qu'à une seule fiche de chaque type (OneToOne).
            autre = type(fiche).objects.filter(utilisateur=utilisateur).exclude(pk=fiche.pk).first()
            if autre is not None:
                return ResultatInvitation(personne, erreur=f'L’email {email} est déjà utilisé par le compte d’une autre fiche ({autre}).')
        else:
            utilisateur = Utilisateur(
                username=_nom_utilisateur_disponible(email), email=email,
                first_name=fiche.prenom, last_name=fiche.nom,
            )
            # Pas de mot de passe tant que la personne n'a pas activé son compte avec le lien.
            utilisateur.set_unusable_password()
            utilisateur.save()

        utilisateur.groups.add(Group.objects.get(name=role))
        if fiche.utilisateur_id != utilisateur.pk:
            fiche.utilisateur = utilisateur
            fiche.save(update_fields=['utilisateur', 'date_modification'])

    if utilisateur.has_usable_password():
        return ResultatInvitation(
            personne, message='Compte déjà activé : la personne se connecte avec son email ; '
                              'en cas d’oubli, elle utilise « Mot de passe oublié ».',
        )

    lien = lien_activation(request, utilisateur)
    texte = (
        f'Bonjour {fiche.prenom}, {nom_centre or "votre centre de formation"} vous a créé un espace personnel. '
        f'Choisissez votre mot de passe avec ce lien (valable 7 jours) : {lien}'
    )
    numero = telephone_international(fiche.telephone)
    return ResultatInvitation(
        personne, lien=lien, message='Lien d’activation créé (valable 7 jours, à usage unique).',
        lien_whatsapp=f'https://wa.me/{numero}?text={quote(texte)}' if numero else '',
    )


def reponse_action_invitation(modeladmin, request, queryset, role):
    """Action d'administration commune (candidats, formateurs) : affiche les liens d'activation à transmettre."""
    from django.template.response import TemplateResponse

    from core.models import ParametresCentre

    centre = ParametresCentre.obtenir()
    resultats = [inviter(request, fiche, role, nom_centre=centre.nom if centre else '') for fiche in queryset]
    contexte = {
        **modeladmin.admin_site.each_context(request),
        'title': 'Accès aux espaces personnels',
        'resultats': resultats,
        'role': role,
        'opts': modeladmin.model._meta,
    }
    return TemplateResponse(request, 'accounts/admin/invitations.html', contexte)
