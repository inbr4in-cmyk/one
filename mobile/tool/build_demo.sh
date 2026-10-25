#!/usr/bin/env bash
# Builds the offline demo (lib/main_demo.dart) as a static site in build/web.
# The result works from any sub-path, loads nothing from other hosts and registers no service worker.
set -euo pipefail
cd "$(dirname "$0")/.."

flutter build web --release -t lib/main_demo.dart --no-web-resources-cdn --no-source-maps --no-wasm-dry-run

python3 - <<'EOF'
import pathlib, re

web = pathlib.Path('build/web')

# Relative paths only: without <base href> every URL resolves against the page itself.
index = web / 'index.html'
html = index.read_text(encoding='utf-8')
html = re.sub(r'\s*<!--(?:(?!-->).)*?base href(?:(?!-->).)*?-->', '', html, flags=re.S)
html = re.sub(r'\s*<base href="[^"]*">', '', html)
html = re.sub(r'<title>.*?</title>', '<title>One English</title>', html, flags=re.S)
style = ('<style>html,body{margin:0;background:#FAF6F3}'
         '@media (prefers-color-scheme: dark){html,body{background:#0A1630}}</style>')
if '<style>' not in html:
    html = html.replace('</head>', f'  {style}\n</head>')
index.write_text(html, encoding='utf-8')

# Local CanvasKit and local font fallbacks (never fonts.gstatic.com); no service worker.
boot = web / 'flutter_bootstrap.js'
js = boot.read_text(encoding='utf-8')
js, n = re.subn(r'_flutter\.loader\.load\(\{.*?\}\);\s*$',
                '_flutter.loader.load({\n  config: {\n    canvasKitBaseUrl: "canvaskit/",\n'
                '    fontFallbackBaseUrl: "assets/fallback-fonts/",\n  },\n});\n', js, flags=re.S)
assert n == 1, 'loader call not found in flutter_bootstrap.js'
boot.write_text(js, encoding='utf-8')

# Only the dart2js CanvasKit build is used: drop the wasm renderers, debug symbols and the service worker.
for p in list(web.rglob('*')):
    if p.is_file() and (p.suffix == '.symbols' or p.name.startswith(('skwasm', 'wimp'))
                        or p.name == 'flutter_service_worker.js' or 'webparagraph' in p.parts):
        p.unlink()
for d in sorted((p for p in web.rglob('*') if p.is_dir()), reverse=True):
    if not any(d.iterdir()):
        d.rmdir()

files = [p for p in web.rglob('*') if p.is_file()]
total = sum(p.stat().st_size for p in files)
big = max(files, key=lambda p: p.stat().st_size)
print(f'demo build: {len(files)} files, {total / 1e6:.1f} MB, largest {big.relative_to(web)} {big.stat().st_size / 1e6:.1f} MB')
EOF
