// Animations du site : apparition au défilement, compteurs, ombre de l'en-tête, carrousels.
// Sans JavaScript ou si le visiteur préfère réduire les animations, tout le contenu reste affiché normalement.
(function () {
  'use strict';

  var mouvementReduit = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Ombre de l'en-tête après défilement
  var entete = document.getElementById('entete');
  if (entete) {
    var majEntete = function () { entete.classList.toggle('est-defile', window.scrollY > 10); };
    window.addEventListener('scroll', majEntete, { passive: true });
    majEntete();
  }

  // Thème clair / sombre : le thème initial est appliqué par le script du <head> (base.html).
  // Le bouton bascule et mémorise le choix ; sans choix mémorisé, on suit la préférence du système.
  var racine = document.documentElement;
  var boutonsTheme = document.querySelectorAll('[data-bouton-theme]');
  var majBoutonsTheme = function () {
    var sombre = racine.getAttribute('data-bs-theme') === 'dark';
    boutonsTheme.forEach(function (bouton) {
      bouton.setAttribute('aria-label', sombre ? 'Activer le mode clair' : 'Activer le mode sombre');
      bouton.setAttribute('aria-pressed', sombre ? 'true' : 'false');
      var icone = bouton.querySelector('.bi');
      if (icone) { icone.className = 'bi ' + (sombre ? 'bi-sun' : 'bi-moon-stars'); }
    });
  };
  var appliquerTheme = function (theme, memoriser) {
    racine.setAttribute('data-bs-theme', theme);
    if (memoriser) {
      try { localStorage.setItem('theme', theme); } catch (e) { /* stockage indisponible : choix non mémorisé */ }
    }
    majBoutonsTheme();
  };
  boutonsTheme.forEach(function (bouton) {
    bouton.addEventListener('click', function () {
      appliquerTheme(racine.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark', true);
    });
  });
  var preferenceSombre = window.matchMedia('(prefers-color-scheme: dark)');
  var suivrePreference = function (evenement) {
    var memorise = null;
    try { memorise = localStorage.getItem('theme'); } catch (e) { /* ignoré */ }
    if (!memorise) { appliquerTheme(evenement.matches ? 'dark' : 'light', false); }
  };
  if (preferenceSombre.addEventListener) { preferenceSombre.addEventListener('change', suivrePreference); }
  majBoutonsTheme();

  // Carrousels ([data-carrousel]) : défilement automatique d'une carte toutes les 5 secondes,
  // retour au début en fin de ligne, boutons précédent / suivant / pause.
  // Le défilement s'arrête au survol, au toucher et quand le carrousel a le focus clavier ;
  // il est désactivé si le visiteur préfère réduire les animations (les boutons restent utilisables).
  var DELAI_DEFILEMENT = 5000;
  document.querySelectorAll('[data-carrousel]').forEach(function (carrousel) {
    var piste = carrousel.querySelector('.carrousel-piste');
    var commandes = carrousel.querySelector('[data-carrousel-commandes]');
    var boutonPause = carrousel.querySelector('[data-carrousel-pause]');
    if (!piste) { return; }

    var minuterie = null;
    var enPause = mouvementReduit;      // pause demandée par le visiteur (bouton) ou préférence système
    var suspendu = false;               // pause temporaire : survol, toucher, focus

    var deborde = function () { return piste.scrollWidth > piste.clientWidth + 2; };
    var pas = function () {
      var carte = piste.firstElementChild;
      var espace = parseFloat(window.getComputedStyle(piste).columnGap) || 0;
      return carte ? carte.getBoundingClientRect().width + espace : piste.clientWidth;
    };
    var defiler = function (sens) {
      var auBout = piste.scrollLeft + piste.clientWidth >= piste.scrollWidth - 2;
      var auDebut = piste.scrollLeft <= 2;
      if (sens > 0 && auBout) {
        piste.scrollTo({ left: 0 });
      } else if (sens < 0 && auDebut) {
        piste.scrollTo({ left: piste.scrollWidth });
      } else {
        piste.scrollBy({ left: sens * pas() });
      }
    };
    var arreter = function () { window.clearInterval(minuterie); minuterie = null; };
    var demarrer = function () {
      arreter();
      if (!enPause && !suspendu && deborde() && !document.hidden) {
        minuterie = window.setInterval(function () { defiler(1); }, DELAI_DEFILEMENT);
      }
    };
    var majPause = function () {
      if (!boutonPause) { return; }
      boutonPause.setAttribute('aria-pressed', enPause ? 'true' : 'false');
      boutonPause.setAttribute('aria-label', enPause ? 'Reprendre le défilement' : 'Mettre en pause le défilement');
      boutonPause.innerHTML = '<i class="bi ' + (enPause ? 'bi-play-fill' : 'bi-pause-fill') + '" aria-hidden="true"></i>';
    };
    var majCommandes = function () {
      if (commandes) { commandes.hidden = !deborde(); }
      demarrer();
    };

    var suivant = carrousel.querySelector('[data-carrousel-suivant]');
    var precedent = carrousel.querySelector('[data-carrousel-precedent]');
    if (suivant) { suivant.addEventListener('click', function () { defiler(1); demarrer(); }); }
    if (precedent) { precedent.addEventListener('click', function () { defiler(-1); demarrer(); }); }
    if (boutonPause) {
      boutonPause.addEventListener('click', function () { enPause = !enPause; majPause(); demarrer(); });
    }

    var suspendre = function () { suspendu = true; arreter(); };
    var reprendre = function () { suspendu = false; demarrer(); };
    carrousel.addEventListener('mouseenter', suspendre);
    carrousel.addEventListener('mouseleave', reprendre);
    carrousel.addEventListener('focusin', suspendre);
    carrousel.addEventListener('focusout', function (evenement) {
      if (!carrousel.contains(evenement.relatedTarget)) { reprendre(); }
    });
    piste.addEventListener('touchstart', suspendre, { passive: true });
    piste.addEventListener('touchend', function () { window.setTimeout(reprendre, DELAI_DEFILEMENT); }, { passive: true });
    document.addEventListener('visibilitychange', demarrer);
    window.addEventListener('resize', majCommandes);

    majPause();
    majCommandes();
  });

  if (mouvementReduit || !('IntersectionObserver' in window)) {
    return;
  }

  // Apparition des blocs [data-anim] quand ils entrent dans l'écran
  document.documentElement.classList.add('animations-actives');
  var observateurApparition = new IntersectionObserver(function (entrees) {
    entrees.forEach(function (entree) {
      if (entree.isIntersecting) {
        entree.target.classList.add('est-visible');
        observateurApparition.unobserve(entree.target);
      }
    });
  }, { threshold: 0.15 });
  document.querySelectorAll('[data-anim]').forEach(function (element) {
    observateurApparition.observe(element);
  });

  // Compteurs : de 0 jusqu'à la valeur réelle affichée par le serveur
  var animerCompteur = function (element) {
    var cible = parseInt(element.getAttribute('data-compteur'), 10);
    if (!cible) { return; }
    var duree = 1500;
    var debut = null;
    var etape = function (instant) {
      if (debut === null) { debut = instant; }
      var progression = Math.min((instant - debut) / duree, 1);
      var adouci = 1 - Math.pow(1 - progression, 3);
      element.textContent = Math.round(cible * adouci).toLocaleString('fr-FR');
      if (progression < 1) { window.requestAnimationFrame(etape); }
    };
    window.requestAnimationFrame(etape);
  };
  var observateurCompteurs = new IntersectionObserver(function (entrees) {
    entrees.forEach(function (entree) {
      if (entree.isIntersecting) {
        animerCompteur(entree.target);
        observateurCompteurs.unobserve(entree.target);
      }
    });
  }, { threshold: 0.6 });
  document.querySelectorAll('[data-compteur]').forEach(function (element) {
    observateurCompteurs.observe(element);
  });
})();
