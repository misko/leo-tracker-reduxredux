# Per-track review display cap

Deployed API/UI release `17484895464c225ebba977487aa36d3d81658bd8` using the
standard immutable release builder and API component selector/restart helpers.
Previous API release: `e55fe6149f45842c53167a48b61f3e0eb2c31c39`.

The UI displays at most 16 per-track TLE review images, ordered by descending
`end_s - start_s`, then observation count and stable track identity. Overview
plots remain visible. Published analysis products and acquisition are unchanged.

Nine tracking-panel tests and the production TypeScript/Vite build passed.
The new API passed its health check after 5086 ms. A Chromium check against the
live UI opened `scan-fw-319730ab74ce43e7` and verified exactly 16 of 57 published
review images, with all three overview images still present. The selected image
names matched an independent duration sort of the published track reviews.
The adaptive acquisition timer remained active.
