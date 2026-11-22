# igi-unc.github.io

Public website for the **Initiative for Generative Immunotherapy (IGI)** at the University of North Carolina at Chapel Hill ([https://igi-unc.github.io/](https://igi-unc.github.io/)).

## Pages

Plain static HTML and CSS with `.nojekyll` (no build step required):

- `index.html` (`/`) — Overview
- `data/index.html` (`/data/`) — Open data policy & tumor/TCR profiling
- `trial/index.html` (`/trial/`) — Head-to-head vaccine trial & open regulatory filings
- `code/index.html` (`/code/`) — Antigen-selection stack (`LENS`, `OpenVax 2`, `Exacto`/`Nexus`, `ImmunoNX`) & `@igi-unc` repositories
- `people/index.html` (`/people/`) — Leadership, UNC collaborators & contact
- `assets/site.css`, `assets/favicon.svg` — Shared stylesheet & icon

## Local preview

```sh
python3 -m http.server 8000
```

GitHub Pages publishes directly from `main` on push.
