// Apply the saved theme before first paint to avoid a flash. A file, not an inline script, so the CSP can forbid inline code.
try {
  var t = localStorage.getItem('oe-theme')
  if (/^(light|dark|ocean|graphite|sand)$/.test(t || '')) document.documentElement.setAttribute('data-theme', t)
} catch (e) {}

// If the app did not start (very old browser, blocked scripts, lost connection), say so instead of an empty screen.
;(function () {
  var failed = false
  function say() {
    var el = document.getElementById('boot-t')
    if (!el) return
    el.innerHTML = 'Страница не открылась. Обновите страницу или откройте ссылку в Chrome или Safari последней версии.<br><br>Бет ашылмады. Бетті жаңартыңыз немесе сілтемені Chrome не Safari соңғы нұсқасында ашыңыз.'
  }
  window.addEventListener('error', function () { failed = true; say() }, true)
  setTimeout(function () { if (failed || document.getElementById('boot')) say() }, 12000)
})()
