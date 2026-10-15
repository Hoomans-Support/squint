/* Starts the first-visit intro. Skipped when the browser is automated (the click-through) unless the URL has ?intro. */
(function () {
  var forced = location.search.indexOf('intro') > -1;
  if (forced || (!navigator.webdriver && SquintIntro.shouldShow())) SquintIntro.show({ logo: 'logo.svg' });
})();
