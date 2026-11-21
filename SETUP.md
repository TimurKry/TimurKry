# How this profile works

Everything visual lives in animated SVGs under `cards/` (light) and `cards/dark/`.
GitHub READMEs can't run JS or load CSS, but `<img>`-embedded SVGs keep their own
`<style>` (CSS keyframes) and SMIL animations.

- `config.json` – name, tagline, tiles (label/title/link), featured repos. **Edit this.**
- `scripts/fetch_data.py` – scrapes the contribution calendar + repo metadata → `data/`
- `scripts/render_readme_cards.py` – draws all cards and regenerates `README.md`
- `.github/workflows/readme.yml` – runs both daily and on every config change
- `fonts/` – Instrument Serif, Geist, Geist Mono (OFL), subset to ASCII, embedded as base64
- `assets/portrait.jpg` (optional) – drop a photo here to replace the monogram with an ASCII portrait

Local preview:

```bash
pip install fonttools brotli pillow numpy
python scripts/fetch_data.py          # or --demo
python scripts/render_readme_cards.py # STATIC=1 for the final frame only
```

Animations are disabled under `prefers-reduced-motion`.
