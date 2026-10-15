// Animations du site : apparition au défilement, compteurs, ombre de l'en-tête.
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
