"""Production du PDF d'un certificat (A4 paysage) avec reportlab.

Le PDF est produit à chaque téléchargement à partir du contenu recopié dans le certificat :
aucun fichier n'est stocké, et le document téléchargé est toujours celui enregistré en base.
"""

import logging
from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import formats
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from core.models import ParametresCentre

from .models import Certificat

logger = logging.getLogger(__name__)

# Couleurs du site (static/css/site.css).
PRIMAIRE = colors.HexColor('#00205b')
ACCENT = colors.HexColor('#d9b000')
TEXTE = colors.HexColor('#444444')
GRIS = colors.HexColor('#777777')

LARGEUR, HAUTEUR = landscape(A4)
CENTRE_X = LARGEUR / 2

TITRES = {
    Certificat.Type.REUSSITE: ('CERTIFICAT DE RÉUSSITE', 'Décerné à'),
    Certificat.Type.PARTICIPATION: ('ATTESTATION DE PARTICIPATION', 'Délivrée à'),
}


def _date(valeur):
    # Usage français : « 1er septembre 2026 », puis « 2 septembre 2026 »…
    jour = '1er' if valeur.day == 1 else str(valeur.day)
    return f"{jour} {formats.date_format(valeur, 'F Y')}"


def _image(champ):
    """ImageReader d'une image enregistrée, ou None si elle est absente ou illisible."""
    if not champ:
        return None
    try:
        with champ.open('rb') as fichier:
            return ImageReader(BytesIO(fichier.read()))
    except (OSError, ValueError):
        logger.warning('Image illisible pour le certificat : %s', champ.name)
        return None


def _dessiner_image(c, image, x_centre, y_bas, largeur_max, hauteur_max):
    largeur, hauteur = image.getSize()
    echelle = min(largeur_max / largeur, hauteur_max / hauteur)
    l, h = largeur * echelle, hauteur * echelle
    c.drawImage(image, x_centre - l / 2, y_bas, l, h, mask='auto')


def _texte_centre(c, texte, police, taille, y, largeur_max=LARGEUR - 160, couleur=TEXTE):
    """Texte centré ; la taille est réduite si le texte est trop long pour la largeur disponible."""
    while taille > 8 and stringWidth(texte, police, taille) > largeur_max:
        taille -= 1
    c.setFont(police, taille)
    c.setFillColor(couleur)
    c.drawCentredString(CENTRE_X, y, texte)


def _qr_code(c, contenu, x, y, taille):
    widget = QrCodeWidget(contenu)
    widget.barLevel = 'M'
    x0, y0, x1, y1 = widget.getBounds()
    dessin = Drawing(taille, taille, transform=[taille / (x1 - x0), 0, 0, taille / (y1 - y0), 0, 0])
    dessin.add(widget)
    renderPDF.draw(dessin, c, x, y)


def generer_pdf(certificat, url_verification):
    """Retourne le PDF du certificat (bytes). `url_verification` est l'adresse complète du QR code."""
    parametres = ParametresCentre.obtenir()
    nom_centre = parametres.nom if parametres else 'Centre de formation'
    titre, formule = TITRES[certificat.type]

    tampon = BytesIO()
    c = canvas.Canvas(tampon, pagesize=(LARGEUR, HAUTEUR))
    c.setTitle(f'{titre.capitalize()} {certificat.numero}')
    c.setAuthor(nom_centre)
    c.setSubject(f'{certificat.formation_titre} — {certificat.titulaire}')

    # Cadre.
    c.setStrokeColor(PRIMAIRE)
    c.setLineWidth(4)
    c.rect(20, 20, LARGEUR - 40, HAUTEUR - 40)
    c.setStrokeColor(ACCENT)
    c.setLineWidth(1)
    c.rect(30, 30, LARGEUR - 60, HAUTEUR - 60)

    # En-tête : logo et nom du centre.
    y = HAUTEUR - 70
    logo = _image(parametres.logo) if parametres else None
    if logo:
        _dessiner_image(c, logo, CENTRE_X, y - 42, 200, 50)
        y -= 62
    _texte_centre(c, nom_centre, 'Helvetica-Bold', 16, y, couleur=PRIMAIRE)
    if parametres and parametres.ville:
        _texte_centre(c, parametres.ville, 'Helvetica', 10, y - 15, couleur=GRIS)

    # Titre, titulaire et objet.
    _texte_centre(c, titre, 'Helvetica-Bold', 30, 375, couleur=PRIMAIRE)
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2)
    c.line(CENTRE_X - 60, 362, CENTRE_X + 60, 362)
    _texte_centre(c, formule, 'Helvetica', 13, 335, couleur=GRIS)
    _texte_centre(c, certificat.titulaire, 'Helvetica-Bold', 28, 300, couleur=colors.black)

    if certificat.type == Certificat.Type.REUSSITE:
        objet = 'pour avoir suivi avec succès la formation'
    else:
        objet = 'pour sa participation à la formation'
    # Le contenu saisi est échappé : Paragraph interprète le balisage XML.
    texte = (
        # Espaces insécables autour des guillemets : « et » ne sont jamais séparés du titre en fin de ligne.
        f'{objet} <b>« {escape(certificat.formation_titre)} »</b>, d’une durée de {certificat.duree_heures} heures, '
        f'du {_date(certificat.date_debut)} au {_date(certificat.date_fin)}.'
    )
    style = ParagraphStyle('corps', fontName='Helvetica', fontSize=14, leading=20, alignment=TA_CENTER, textColor=TEXTE)
    paragraphe = Paragraph(texte, style)
    _, hauteur = paragraphe.wrap(LARGEUR - 220, 100)
    paragraphe.drawOn(c, 110, 275 - hauteur)

    # Pied : QR code (gauche), lieu et date (centre), signature (droite).
    _qr_code(c, url_verification, 60, 55, 80)
    c.setFont('Helvetica', 8)
    c.setFillColor(GRIS)
    c.drawString(60, 45, 'Vérifier ce document')

    lieu = f'Fait à {parametres.ville}, le' if parametres and parametres.ville else 'Délivré le'
    _texte_centre(c, f'{lieu} {_date(certificat.date_delivrance)}', 'Helvetica', 11, 110)
    _texte_centre(c, f'N° {certificat.numero}', 'Helvetica-Bold', 11, 92, couleur=PRIMAIRE)

    x_signature = LARGEUR - 170
    if certificat.signataire_fonction:
        c.setFont('Helvetica-Bold', 11)
        c.setFillColor(TEXTE)
        c.drawCentredString(x_signature, 150, certificat.signataire_fonction)
    signature = _image(parametres.signature) if parametres else None
    if signature:
        _dessiner_image(c, signature, x_signature, 75, 170, 65)
    if certificat.signataire_nom:
        c.setFont('Helvetica', 11)
        c.setFillColor(TEXTE)
        c.drawCentredString(x_signature, 60, certificat.signataire_nom)

    # Un certificat annulé reste consultable par le centre, avec une mention bien visible.
    if not certificat.est_valide:
        c.saveState()
        c.setFillColor(colors.Color(0.8, 0, 0, alpha=0.25))
        c.setFont('Helvetica-Bold', 110)
        c.translate(CENTRE_X, HAUTEUR / 2)
        c.rotate(25)
        c.drawCentredString(0, -40, 'ANNULÉ')
        c.restoreState()

    c.showPage()
    c.save()
    return tampon.getvalue()
