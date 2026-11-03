#!/usr/bin/env bash
# Download the front-end libraries once into frontend/vendor so the app works offline and under a strict
# Content-Security-Policy (no CDNs). Needs Node/npm and internet access; re-run to refresh.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=frontend/vendor
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT/katex" "$OUT/pyodide" "$OUT/fonts"
fetch() { # name@version
  (cd "$TMP" && npm pack --silent "$1" >/dev/null && mkdir -p "x-$2" && tar -xzf ./*"$2"*.tgz -C "x-$2" --strip-components=1 && rm -f ./*"$2"*.tgz)
}
fetch marked@12.0.2 marked;      cp "$TMP/x-marked/marked.min.js" "$OUT/marked.min.js"
fetch dompurify@3.1.6 dompurify; cp "$TMP/x-dompurify/dist/purify.min.js" "$OUT/purify.min.js"
fetch katex@0.16.11 katex;       cp "$TMP/x-katex/dist/katex.min.js" "$TMP/x-katex/dist/katex.min.css" "$OUT/katex/"; rm -rf "$OUT/katex/fonts"; cp -r "$TMP/x-katex/dist/fonts" "$OUT/katex/fonts"
# only keep the modern woff2 fonts (every current browser supports them)
sed -i -E 's/,url\([^)]*\.woff\) format\("woff"\)//g; s/,url\([^)]*\.ttf\) format\("truetype"\)//g' "$OUT/katex/katex.min.css"
find "$OUT/katex/fonts" -type f ! -name '*.woff2' -delete
fetch @fontsource/opendyslexic@5.1.0 opendyslexic 2>/dev/null || fetch @fontsource/opendyslexic opendyslexic
cp "$TMP"/x-opendyslexic/files/opendyslexic-latin-400-normal.woff2 "$TMP"/x-opendyslexic/files/opendyslexic-latin-700-normal.woff2 "$OUT/fonts/" 2>/dev/null || true
fetch pyodide@0.26.4 pyodide
for f in pyodide.js pyodide.asm.js pyodide.asm.wasm python_stdlib.zip pyodide-lock.json; do cp "$TMP/x-pyodide/$f" "$OUT/pyodide/"; done
echo "vendored: $(du -sh "$OUT" | cut -f1)"
