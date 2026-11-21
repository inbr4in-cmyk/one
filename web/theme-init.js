// Apply the saved theme before first paint to avoid a flash. A file, not an inline script, so the CSP can forbid inline code.
try {
  var t = localStorage.getItem('oe-theme')
  if (/^(light|dark|ocean|graphite|sand)$/.test(t || '')) document.documentElement.setAttribute('data-theme', t)
} catch (e) {}
