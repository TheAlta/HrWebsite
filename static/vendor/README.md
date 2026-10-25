# Vendored frontend libraries

Self-hosted on purpose (no external CDN — spec section 14, risk "external services").
The version is in the file name; update by replacing the file and the reference in `templates/base.html`.

| File | Source |
|---|---|
| `htmx-2.0.11.min.js` | npm `htmx.org@2.0.11` → `dist/htmx.min.js` |
| `alpine-3.17.5.min.js` | npm `alpinejs@3.17.5` → `dist/cdn.min.js` |
| `../fonts/vazirmatn/Vazirmatn-Variable.woff2` | npm `vazirmatn@33.0.3` → `fonts/webfonts/Vazirmatn[wght].woff2` (OFL licence) |
