// Page translators rewrite the tab title too, and it holds proper names (the
// deck name, the app name). translate="no" on <title> is not honoured by every
// translator, so put the original text back whenever it changes.
(function () {
  var title = document.querySelector("title");
  if (!title) return;
  var original = title.textContent;
  new MutationObserver(function () {
    if (title.textContent !== original) title.textContent = original;
  }).observe(title, { childList: true, characterData: true, subtree: true });
})();
