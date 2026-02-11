# Contraceptive Reddit Tracker — Multi-Subreddit

## What this project does
Scrapes **8 subreddits** for contraceptive discussions, identifies mentions of ~26 contraceptive types and ~24 side effects using regex (with misspellings/slang), runs keyword-based sentiment analysis, computes engagement scores, stores everything in SQLite, and serves a web dashboard with charts, heatmaps, subreddit filtering, and a post/comment explorer.

## Subreddits scraped
| Subreddit | Posts per cycle | Notes |
|-----------|----------------|-------|
| r/birthcontrol | 200 /new + 50 /hot | Primary source |
| r/TwoXChromosomes | 100 /new + 50 /hot | |
| r/abortion | 100 /new + 50 /hot | |
| r/prochoice | 100 /new + 50 /hot | |
| r/prolife | 100 /new + 50 /hot | |
| r/sex | 100 /new + 50 /hot | |
| r/AskDocs | 100 /new + 50 /hot | |
| r/WomensHealth | 100 /new + 50 /hot | |

## Project structure
```
reddit-bc-tracker/
  bc_tracker.py        # Core: scraping, regex, sentiment, SQLite, CLI
  bc_tracker_web.py    # Web server + dashboard (auto-scrapes every 6 hours)
  generate_site.py     # Static site generator → docs/index.html for GitHub Pages
  CLAUDE.md            # This file — project reference for Claude
  docs/
    index.html         # Auto-generated interactive dashboard (GitHub Pages)
  bc_tracker_data/
    tracker.db         # SQLite database (posts, comments, mentions, side effects)
    scrape_errors.log  # Error log file (WARNING+ level)
    daily_mentions.json # Legacy data (migrated, kept as backup)
```

Backups go to: `~/Library/CloudStorage/Dropbox-Personal/backups/reddit-bc-tracker/`

## How to run

### Web dashboard (primary)
```bash
cd ~/projects/reddit-bc-tracker && python3 bc_tracker_web.py
# http://localhost:8050 — auto-scrapes every 6 hours
```

### Static site (GitHub Pages)
```bash
python3 generate_site.py              # Generate docs/index.html only
python3 generate_site.py --push       # Generate + git commit + push to GitHub
```

### CLI
```bash
python3 bc_tracker.py scrape --all     # Scrape all subs, posts + comments
python3 bc_tracker.py report --days 30 # Report with sentiment + side effects
python3 bc_tracker.py report --csv     # Export CSV
```

## Architecture

- **Zero external dependencies** — Python 3.9 stdlib only (sqlite3, http.server, urllib, threading, logging)
- **SQLite WAL mode** — concurrent reads during scrapes
- **Reddit public JSON API** — no API keys, 1.5s rate-limit delay
- **Multi-subreddit** — loops 8 subs, scrapes /new + /hot per sub
- **Cross-post dedup** — detects Reddit crosspost_parent, skips duplicate mention/effect analysis
- **Engagement scoring** — `log2(score) + log2(comments) * 1.5`
- **Structured logging** — Python logging module to console (INFO) + file (WARNING+) + DB table
- **In-process scheduler** — threading.Timer every 6 hours
- **Auto-backup** — SQLite online backup API to Dropbox after each scrape, 7-day rotation
- **URL state** — filter state (date range + subreddit) encoded in URL hash fragment for bookmarking/sharing
- **CSV export** — client-side CSV generation from loaded data via JS Blob
- **GitHub Pages static site** — `generate_site.py` bakes all raw data into `docs/index.html` with client-side filtering (date range, subreddit), charts, post explorer with comments — auto-published after each scrape via git push
- **Auto-publish** — after each scrape (scheduled or manual), `generate_site.py --push` regenerates HTML and pushes to GitHub Pages

## Database schema (tracker.db)

- **posts** — id, title, selftext, created_utc, score, num_comments, permalink, first_seen, sentiment (float), comments_scraped (0/1), subreddit, engagement_score, sort_source ('new'/'hot'), crosspost_parent
- **comments** — id, post_id, body, score, created_utc, author, sentiment, first_seen
- **mentions** — post_id, contraceptive (composite PK). Links posts to contraceptive types found in post OR comment text.
- **side_effects** — source_type ('post'/'comment'), source_id, effect (composite PK)
- **scrape_runs** — id, scraped_at, post_count, subreddit, error_count
- **scrape_errors** — id, timestamp, subreddit, error_type, message, source_id, source_type

## Key features

### Multi-subreddit scraping
- Scrapes 8 subreddits per cycle (configurable in `SUBREDDITS` list)
- Both /new and /hot sort orders for visibility signal
- Per-sub error handling — one failure doesn't kill the cycle
- ~5-8 minutes total scrape time per cycle

### Cross-post deduplication
- Detects Reddit's `crosspost_parent_list` field
- Cross-posted content is stored but mentions/side-effects are not duplicated
- Same-ID posts (from /new vs /hot overlap) handled by ON CONFLICT

### Engagement scoring
- Formula: `log2(max(upvotes, 1)) + log2(max(comments, 1)) * 1.5`
- Weights discussion (comments) higher than upvotes
- Posts found in /hot get `sort_source = 'hot'` (visibility signal)
- Post Explorer sorted by engagement score (not just upvotes)

### Comment scraping
- After post scraping, fetches comments for up to 50 posts per cycle
- Walks the full comment reply tree recursively
- Comments are analyzed for mentions, sentiment, and side effects

### Sentiment analysis
- Keyword-based scorer: positive/negative word lists + intensifiers + negators
- Score range: -1.0 (very negative) to +1.0 (very positive), null if no sentiment words
- Stored per-post and per-comment
- Dashboard shows average sentiment per contraceptive type

### Error logging
- Python `logging` module: INFO to console, WARNING+ to `bc_tracker_data/scrape_errors.log`
- Errors also stored in `scrape_errors` DB table for API access
- Dashboard shows "Errors 24h" stat (green if 0, red if >0)
- `/api/errors` endpoint for viewing recent errors

### Side effect tracking (24 categories)
Bleeding/spotting, Cramping, Weight gain, Weight loss, Acne, Hair loss, Mood swings, Depression, Anxiety, Headaches, Nausea, Fatigue, Low libido, Breast tenderness, Bloating, Back pain, Insertion pain, Removal pain, Infection, Strings/displacement, Expulsion, Blood clots/DVT, Brain fog, Dizziness

### Contraceptive types tracked (26)
Mirena, Kyleena, Liletta, Skyla, Paragard, IUD (general), Nexplanon, Combined pill, Mini pill, The pill (general), Depo-Provera, NuvaRing, Xulane patch, Plan B, Condoms, Spermicide, Diaphragm, FAM/NFP, Withdrawal, Slynd, Yaz, Lo Loestrin, Phexxi, Ortho Tri-Cyclen, Junel, Seasonique, Sprintec

Keywords include common misspellings (merina, paraguard, kylena, nexplanion) and slang (copper T, bc shot, bc patch, nuva ring, ec pill, pull out method, basal body temp, etc.)

## Web API endpoints

All data endpoints accept `?from=YYYY-MM-DD&to=YYYY-MM-DD&sub=birthcontrol` for date range and subreddit filtering.

- `GET /` — dashboard
- `GET /api/data?from=2026-02-01&to=2026-02-11&sub=` — mention counts, daily breakdown, DB stats
- `GET /api/sentiment?from=&to=&sub=` — avg sentiment per contraceptive type
- `GET /api/side-effects?from=&to=&type=Mirena&sub=` — side-effect counts (optionally filtered)
- `GET /api/side-effects-heatmap?from=&to=&sub=` — {contraceptive: {effect: count}} matrix
- `GET /api/posts?type=Mirena&limit=20&from=&to=&sub=` — top posts with sentiment + engagement
- `GET /api/comments?post_id=abc123` — comments for a post
- `GET /api/post-effects?id=abc123` — side effects for a specific post
- `GET /api/validate?section=sentiment` — validation examples with step-by-step analysis
- `GET /api/errors?limit=50` — recent scrape errors
- `GET /api/status` — scheduler status
- `POST /api/scrape` — trigger immediate scrape

## Dashboard sections

1. **Stats row** — posts, comments, mentions, avg sentiment, subreddits, types, errors 24h
2. **Mentions by Type** — horizontal bar chart
3. **Sentiment by Type** — bar chart green (positive) to red (negative)
4. **Daily Trend** — line chart, top 5 types over time
5. **Side Effect Heatmap** — contraceptive x side-effect matrix with color intensity
6. **Top Side Effects** — ranked bar chart of most-discussed worries
7. **Category Breakdown** — doughnut chart (IUDs, Pills, Long-acting, etc.)
8. **Post Explorer** — browse posts by type, see subreddit badge, engagement score, sentiment badges, side-effect pills, expandable comments
- Each section has **Methods** button (methodology description) and **Validate** button (real examples with step-by-step analysis)
- **Subreddit filter** dropdown in header
- **Date range picker** — From/To date inputs + quick presets (7d/30d/90d/All)
- **CSV export** button — downloads summary CSV (contraceptive, mentions, avg sentiment, post count) respecting current filters
- **Shareable URLs** — filter state encoded in URL hash (`#from=2026-02-01&to=2026-02-11&sub=birthcontrol`), bookmarkable and shareable

## Key functions in bc_tracker.py

- `run_scrape()` — full multi-sub cycle: all subs + comments + sentiment + effects + backup
- `scrape_subreddit(subreddit, limit, sort)` — fetch posts from one sub/sort
- `compute_engagement(score, num_comments)` — engagement score formula
- `save_posts_to_db()` — upsert with engagement, crosspost dedup
- `score_sentiment(text)` — keyword-based scorer, returns -1.0 to 1.0
- `find_mentions(text)` / `find_side_effects(text)` — regex matching
- `scrape_comments_batch(conn, limit)` — fetch comments for unscraped posts
- `backfill_sentiment_and_effects(conn)` — backfill sentiment, engagement, and new keyword matches
- `save_error_to_db()` — log error to DB
- `export_all_data(conn)` — returns all raw data as dicts for static site generation
- `query_*()` — all query functions accept `date_from`, `date_to` (unix timestamps) + `subreddit` for filtering

## Common tasks

### Add a new subreddit
Edit `SUBREDDITS` list in `bc_tracker.py` (~line 65). Add `{"name": "SubName", "limit": 100}`.

### Add a new contraceptive type
Edit `CONTRACEPTIVES` dict in `bc_tracker.py` (~line 90). Add key + regex. Also add to `CATS` in `bc_tracker_web.py`.

### Add a new side effect
Edit `SIDE_EFFECTS` dict in `bc_tracker.py` (~line 115). Add key + regex.

### Change auto-scrape interval
Edit `SCRAPE_INTERVAL` in `bc_tracker_web.py` (default: `6 * 60 * 60`).

### Change port
Edit `PORT` in `bc_tracker_web.py` (default: 8050).

### Back up / restore
- Backups: `~/Library/CloudStorage/Dropbox-Personal/backups/reddit-bc-tracker/`
- Restore: copy `tracker-YYYY-MM-DD.db` to `bc_tracker_data/tracker.db`
- Scripts are also backed up there (bc_tracker.py, bc_tracker_web.py, CLAUDE.md)

### Set up GitHub Pages (one-time)
1. Create GitHub repo (e.g., `bc-tracker`)
2. `cd ~/projects/reddit-bc-tracker && git init && git remote add origin git@github.com:<username>/bc-tracker.git`
3. Enable GitHub Pages in repo settings: source = `docs/` folder, branch = `main`
4. First push: `python3 generate_site.py && git add -A && git commit -m "Initial commit" && git push -u origin main`
5. URL: `https://<username>.github.io/bc-tracker/`
6. After setup, auto-publish works: each scrape regenerates + pushes `docs/index.html`

## Known limitations
- Sentiment is keyword-based (no ML). Adequate for trend detection, not precise per-post.
- Reddit public API may rate-limit. Full multi-sub cycle takes ~5-8 min.
- `created_utc` for legacy-migrated posts is 0.
- Web server is single-threaded (fine for personal use).
- Side-effect regex may over-match (e.g., "anxiety about getting pregnant" matches "anxiety").
- Cross-post detection only catches Reddit's native crosspost mechanism, not manual reposts.

## History
- **2026-02-09** — Initial version: JSON storage, CLI, post scraping
- **2026-02-09** — Web dashboard with Chart.js
- **2026-02-10** — SQLite database, auto-scrape scheduler, post explorer, Dropbox backup
- **2026-02-10** — Moved to ~/projects/reddit-bc-tracker, added script backup
- **2026-02-11** — Comment scraping, sentiment analysis, side-effect tracker, heatmap dashboard
- **2026-02-11** — Methods and Validate buttons for transparency
- **2026-02-11** — Multi-subreddit expansion (8 subs), expanded keywords with misspellings/slang (26 types), cross-post dedup, structured error logging, engagement scoring, subreddit filter
- **2026-02-11** — Custom date range picker (From/To + presets), CSV export, shareable URL state encoding
- **2026-02-11** — GitHub Pages static site generator (`generate_site.py`): self-contained interactive dashboard with client-side filtering, auto-publish after each scrape (replaces old HTML export)
