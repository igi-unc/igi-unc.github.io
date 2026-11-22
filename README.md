# igi-unc.github.io

Public website for the **Initiative for Generative Immunotherapy (IGI)** at the University of North Carolina at Chapel Hill ([https://igi-unc.github.io/](https://igi-unc.github.io/)).

## Structure

Plain static HTML and CSS with `.nojekyll`—no build step required:

- `index.html` — main single-page site
- `assets/site.css` — layout, typography, and light/dark theme styles
- `404.html` — fallback error page

## Local preview

Open `index.html` directly in a browser, or serve locally:

```sh
python3 -m http.server 8000
```

GitHub Pages publishes straight from the `main` branch on push.
