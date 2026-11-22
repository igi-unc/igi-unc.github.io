# igi-unc.github.io

Public website for the **Initiative for Generative Immunotherapy (IGI)** at the University of North Carolina at Chapel Hill ([https://igi-unc.github.io/](https://igi-unc.github.io/)).

## Pages

Plain static HTML and CSS with `.nojekyll` (no local build step required):

- `index.html` (`/`) — Overview + live Substack feed of IGI posts
- `data/index.html` (`/data/`) — Open data policy, biobanks & tumor/TCR profiling
- `trial/index.html` (`/trial/`) — Head-to-head vaccine trial & open regulatory filings
- `code/index.html` (`/code/`) — Candidate-antigen software union (`Nexus`/`Exacto`, `LENS`, `OpenVax 2`, `ImmunoNX`) & `@igi-unc` repositories
- `people/index.html` (`/people/`) — Leadership, PIRL overlap & specimen/clinical partners
- `projects/index.html` (`/projects/`) — Exploratory & supporting projects
- `assets/site.css`, `assets/favicon.svg` — Shared stylesheet & icon

## Blog sync (`pirlblog.substack.com` → IGI feed)

`.github/workflows/sync-blog.yml` runs `python3 scripts/sync_posts.py` hourly (reusing the public PIRL Google Cloud Substack cache so GitHub Actions runner IPs are never blocked by Substack) and updates `data/posts.json` and `index.html` whenever a new IGI post is published.

A post on `pirlblog.substack.com` appears in the IGI feed if **any** of the following holds:

1. **Substack section or tag:** Placed in an `IGI` section (`https://pirlblog.substack.com/s/igi`) or tagged `igi` (`https://pirlblog.substack.com/t/igi`). *(Note: Substack strips post tags from its main RSS `/feed`; creating a Substack **Section** named `IGI` gives it a dedicated URL `/s/igi` and RSS `/s/igi/feed`, or mentioning `IGI` in the subtitle/opening text works automatically via the existing GCP cache.)*
2. **Title / subtitle / opening text:** Mentions `IGI` or `Initiative for Generative Immunotherapy`.
3. **Explicit pin:** Listed in `include_urls` inside `data/blog_config.json` (and any URL in `exclude_urls` is hidden).

To refresh locally:

```sh
python3 scripts/sync_posts.py
```

## Local preview

```sh
python3 -m http.server 8000
```
