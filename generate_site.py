#!/usr/bin/env python3
"""
Generate a self-contained interactive dashboard as docs/index.html.

Usage:
    python3 generate_site.py            # Generate only
    python3 generate_site.py --push     # Generate + git commit + push
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bc_tracker as tracker

DOCS_DIR = Path(__file__).parent / "docs"


def generate_html(data: dict) -> str:
    """Build the full self-contained HTML dashboard string."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    stats = data["stats"]

    posts_json = json.dumps(data["posts"], separators=(",", ":"))
    mentions_json = json.dumps(data["mentions"], separators=(",", ":"))
    effects_json = json.dumps(data["side_effects"], separators=(",", ":"))
    comments_json = json.dumps(data["comments"], separators=(",", ":"))
    stats_json = json.dumps(stats, separators=(",", ":"))
    validation_json = json.dumps(data["validation"], separators=(",", ":"))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Contraceptive Reddit Tracker</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  :root {{
    --bg: #0f1117; --surface: #1a1d27; --border: #2a2d3a;
    --text: #e1e4ed; --muted: #8b90a0;
    --accent: #7c6ef0; --accent2: #e06090; --green: #4ade80;
    --yellow: #f0c040; --red: #f06060; --cyan: #40d0d0;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.5; }}

  header {{ background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 1.25rem 2rem; display: flex; align-items: center;
    justify-content: space-between; flex-wrap: wrap; gap: 1rem; }}
  header h1 {{ font-size: 1.35rem; font-weight: 600; }}
  header h1 span {{ color: var(--accent); }}
  .controls {{ display: flex; gap: .75rem; align-items: center; flex-wrap: wrap; }}
  select, button, input[type="date"] {{ background: var(--bg); color: var(--text); border: 1px solid var(--border);
    padding: .5rem 1rem; border-radius: 8px; font-size: .875rem; cursor: pointer; }}
  input[type="date"] {{ cursor: text; width: 140px; }}
  input[type="date"]::-webkit-calendar-picker-indicator {{ filter: invert(0.8); }}
  button:hover {{ border-color: var(--accent); }}
  .preset-btn {{ padding: .35rem .6rem; font-size: .75rem; border-radius: 6px; }}
  .preset-btn.active {{ border-color: var(--accent); color: var(--accent); background: rgba(124,110,240,0.1); }}
  .date-label {{ font-size: .75rem; color: var(--muted); margin-right: 2px; }}
  .updated-label {{ font-size: .8rem; color: var(--muted); }}

  main {{ max-width: 1280px; margin: 0 auto; padding: 1.5rem; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 1rem; margin-bottom: 1.5rem; }}
  .stat-card {{ background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1.1rem; }}
  .stat-card .label {{ font-size: .7rem; color: var(--muted); text-transform: uppercase;
    letter-spacing: .05em; margin-bottom: .2rem; }}
  .stat-card .value {{ font-size: 1.6rem; font-weight: 700; }}
  .stat-card .sub {{ font-size: .65rem; color: var(--muted); margin-top: .1rem; }}
  .accent {{ color: var(--accent); }} .accent2 {{ color: var(--accent2); }}
  .green {{ color: var(--green); }} .yellow {{ color: var(--yellow); }}
  .cyan {{ color: var(--cyan); }} .red {{ color: var(--red); }}

  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 1.5rem; }}
  @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  .card {{ background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1.5rem; }}
  .card h2 {{ font-size: .95rem; margin-bottom: 1rem; font-weight: 600; }}
  .card.full {{ grid-column: 1 / -1; }}

  .bar-row {{ display: flex; align-items: center; margin-bottom: .4rem; gap: .5rem; }}
  .bar-label {{ width: 130px; font-size: .75rem; text-align: right; flex-shrink: 0;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .bar-track {{ flex: 1; height: 20px; background: var(--bg); border-radius: 4px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 4px; transition: width .5s ease; min-width: 2px; }}
  .bar-count {{ width: 36px; font-size: .75rem; color: var(--muted); text-align: right; flex-shrink: 0; }}

  .chart-container {{ position: relative; height: 280px; }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .82rem; }}
  th {{ text-align: left; color: var(--muted); font-weight: 500; padding: .5rem .6rem;
    border-bottom: 1px solid var(--border); font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; }}
  td {{ padding: .5rem .6rem; border-bottom: 1px solid var(--border); }}
  tr:last-child td {{ border-bottom: none; }}
  .post-link {{ color: var(--accent); text-decoration: none; }}
  .post-link:hover {{ text-decoration: underline; }}
  .empty {{ text-align: center; color: var(--muted); padding: 2rem 1rem; }}
  .pill {{ display: inline-block; padding: 2px 7px; border-radius: 10px; font-size: .65rem;
    background: var(--bg); border: 1px solid var(--border); margin: 1px 2px; }}
  .pill.pos {{ border-color: var(--green); color: var(--green); }}
  .pill.neg {{ border-color: var(--red); color: var(--red); }}
  .pill.neu {{ border-color: var(--muted); color: var(--muted); }}
  .pill.effect {{ border-color: var(--yellow); color: var(--yellow); }}

  .explorer-controls {{ display: flex; gap: .75rem; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; }}
  .post-text {{ font-size: .78rem; color: var(--muted); margin-top: .2rem;
    max-height: 60px; overflow: hidden; white-space: pre-wrap; word-break: break-word; }}
  .post-text.expanded {{ max-height: none; }}
  .toggle-text {{ color: var(--accent); cursor: pointer; font-size: .7rem; }}

  .heatmap {{ overflow-x: auto; }}
  .heatmap table {{ font-size: .7rem; }}
  .heatmap th {{ padding: .3rem .4rem; white-space: nowrap; }}
  .heatmap td {{ padding: .3rem .4rem; text-align: center; min-width: 32px; }}
  .heatmap .row-label {{ text-align: right; font-weight: 500; white-space: nowrap; }}
  .heat-cell {{ border-radius: 3px; min-width: 28px; display: inline-block; padding: 1px 4px; }}

  .sent-bar {{ display: flex; align-items: center; gap: .4rem; }}
  .sent-track {{ width: 80px; height: 12px; background: var(--bg); border-radius: 6px; overflow: hidden;
    position: relative; }}
  .sent-fill {{ height: 100%; border-radius: 6px; position: absolute; top: 0; }}
  .sent-val {{ font-size: .7rem; width: 40px; }}

  .comments-section {{ margin-top: .5rem; padding: .5rem; background: var(--bg); border-radius: 8px; font-size: .78rem; }}
  .comment-item {{ padding: .4rem 0; border-bottom: 1px solid var(--border); }}
  .comment-item:last-child {{ border-bottom: none; }}
  .comment-meta {{ font-size: .65rem; color: var(--muted); }}

  .export-btn {{ background: none; border: 1px solid var(--border); color: var(--muted);
    padding: .4rem .8rem; border-radius: 8px; font-size: .8rem; }}
  .export-btn:hover {{ border-color: var(--green); color: var(--green); }}

  .card-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }}
  .card-header h2 {{ margin-bottom: 0; }}
  .methods-btn {{ background: none; border: 1px solid var(--border); color: var(--muted);
    padding: 2px 8px; border-radius: 6px; font-size: .65rem; cursor: pointer;
    text-transform: uppercase; letter-spacing: .04em; transition: all .2s; }}
  .methods-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
  .methods-btn.active {{ border-color: var(--accent); color: var(--accent); background: rgba(124,110,240,0.1); }}
  .methods-box {{ display: none; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: .8rem 1rem; margin-bottom: 1rem; font-size: .78rem;
    line-height: 1.6; color: var(--muted); }}
  .methods-box.visible {{ display: block; }}
  .methods-box strong {{ color: var(--text); }}
  .methods-box ul {{ margin: .3rem 0 .3rem 1.2rem; }}
  .methods-box li {{ margin-bottom: .15rem; }}
  .methods-box code {{ background: var(--surface); padding: 1px 4px; border-radius: 3px; font-size: .72rem; }}

  .validate-btn {{ background: none; border: 1px solid var(--border); color: var(--muted);
    padding: 2px 8px; border-radius: 6px; font-size: .65rem; cursor: pointer;
    text-transform: uppercase; letter-spacing: .04em; transition: all .2s; margin-left: 4px; }}
  .validate-btn:hover {{ border-color: var(--cyan); color: var(--cyan); }}
  .validate-btn.active {{ border-color: var(--cyan); color: var(--cyan); background: rgba(64,208,208,0.1); }}
  .validate-box {{ display: none; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: .8rem 1rem; margin-bottom: 1rem; font-size: .78rem; line-height: 1.6; }}
  .validate-box.visible {{ display: block; }}
  .val-example {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
    padding: .6rem .8rem; margin-bottom: .6rem; }}
  .val-example:last-child {{ margin-bottom: 0; }}
  .val-title {{ font-weight: 600; font-size: .8rem; margin-bottom: .3rem; color: var(--text); }}
  .val-text {{ font-size: .75rem; color: var(--muted); margin-bottom: .4rem;
    white-space: pre-wrap; word-break: break-word; line-height: 1.5; }}
  .val-text .hl-pos {{ background: rgba(74,222,128,0.2); color: var(--green); border-radius: 2px; padding: 0 2px; }}
  .val-text .hl-neg {{ background: rgba(240,96,96,0.2); color: var(--red); border-radius: 2px; padding: 0 2px; }}
  .val-text .hl-negator {{ background: rgba(240,192,64,0.15); color: var(--yellow); border-radius: 2px; padding: 0 2px; }}
  .val-text .hl-intensifier {{ background: rgba(124,110,240,0.15); color: var(--accent); border-radius: 2px; padding: 0 2px; }}
  .val-text .hl-mention {{ background: rgba(124,110,240,0.25); color: var(--accent); border-radius: 2px; padding: 0 2px; font-weight: 600; }}
  .val-text .hl-effect {{ background: rgba(240,192,64,0.25); color: var(--yellow); border-radius: 2px; padding: 0 2px; font-weight: 600; }}
  .val-steps {{ font-size: .7rem; color: var(--muted); margin-top: .3rem; }}
  .val-steps table {{ font-size: .7rem; }}
  .val-steps td {{ padding: .15rem .4rem; border-bottom: 1px solid var(--border); }}
  .val-summary {{ font-size: .75rem; font-weight: 600; margin-top: .4rem; padding: .3rem .5rem;
    background: var(--bg); border-radius: 4px; }}
</style>
</head>
<body>

<header>
  <h1><span>Contraceptive</span> &mdash; Reddit Tracker</h1>
  <div class="controls">
    <select id="subFilter">
      <option value="">All subreddits</option>
      <option value="birthcontrol">r/birthcontrol</option>
      <option value="TwoXChromosomes">r/TwoXChromosomes</option>
      <option value="abortion">r/abortion</option>
      <option value="prochoice">r/prochoice</option>
      <option value="prolife">r/prolife</option>
      <option value="sex">r/sex</option>
      <option value="AskDocs">r/AskDocs</option>
      <option value="WomensHealth">r/WomensHealth</option>
    </select>
    <span class="date-label">From</span><input type="date" id="dateFrom">
    <span class="date-label">To</span><input type="date" id="dateTo">
    <button class="preset-btn" onclick="setPreset(7)" id="pre7">7d</button>
    <button class="preset-btn" onclick="setPreset(30)" id="pre30">30d</button>
    <button class="preset-btn" onclick="setPreset(90)" id="pre90">90d</button>
    <button class="preset-btn" onclick="setPreset(0)" id="pre0">All</button>
    <button class="export-btn" onclick="exportCSV()">Export CSV</button>
    <span class="updated-label">Last updated: {now}</span>
  </div>
</header>

<main>
  <div class="stats" id="statsRow"></div>
  <div class="grid">
    <div class="card">
      <div class="card-header"><h2>Mentions by Type</h2><div><button class="methods-btn" onclick="toggleMethods('m-mentions')">Methods</button><button class="validate-btn" onclick="toggleValidate('v-mentions','mentions')">Validate</button></div></div>
      <div class="methods-box" id="m-mentions">
        <strong>How mentions are counted:</strong> Posts are scraped from <strong>8 subreddits</strong>: r/birthcontrol (primary, 200 posts), r/TwoXChromosomes, r/abortion, r/prochoice, r/prolife, r/sex, r/AskDocs, r/WomensHealth (100 each). Both /new and /hot sort orders are scraped per sub for broader coverage. Each post title, body text, and comment is scanned against <strong>26 regex patterns</strong> &mdash; one per contraceptive type, including common misspellings and slang (e.g., "merina" &rarr; Mirena, "paraguard" &rarr; Paragard, "copper T" &rarr; Paragard, "bc shot" &rarr; Depo-Provera). The "IUD (general)" category uses a negative lookahead to avoid double-counting when a specific brand is also named. <strong>Cross-posted content</strong> is detected and deduplicated. Counts reflect the number of <strong>unique posts + comments</strong> mentioning each type, not total word occurrences.
      </div>
      <div class="validate-box" id="v-mentions"></div>
      <div id="barChart"></div>
    </div>
    <div class="card">
      <div class="card-header"><h2>Sentiment by Type</h2><div><button class="methods-btn" onclick="toggleMethods('m-sentiment')">Methods</button><button class="validate-btn" onclick="toggleValidate('v-sentiment','sentiment')">Validate</button></div></div>
      <div class="methods-box" id="m-sentiment">
        <strong>Keyword-based sentiment scoring:</strong> Each post/comment (across all 8 subreddits) is scored from <strong>-1.0</strong> (very negative) to <strong>+1.0</strong> (very positive) using curated word lists:
        <ul>
          <li><strong>~40 positive words</strong> (love, recommend, effective, relief, helped, works, etc.)</li>
          <li><strong>~50 negative words</strong> (hate, pain, nightmare, frustrated, scared, bleeding, etc.)</li>
          <li><strong>Negators</strong> (not, never, don't, etc.) flip the next word's polarity &mdash; "not painful" counts as positive</li>
          <li><strong>Intensifiers</strong> (very, extremely, so) multiply the next word's weight by 1.5x</li>
        </ul>
        <strong>Score formula:</strong> <code>(positive - negative) / total_sentiment_words</code>, clamped to [-1, 1]. The chart shows the <strong>average score</strong> across all posts mentioning each type. This is best for <strong>comparing trends between types</strong>, not interpreting individual posts &mdash; it cannot detect sarcasm, context, or complex phrasing.
      </div>
      <div class="validate-box" id="v-sentiment"></div>
      <div id="sentChart"></div>
    </div>
    <div class="card full">
      <div class="card-header"><h2>Daily Trend</h2><div><button class="methods-btn" onclick="toggleMethods('m-trend')">Methods</button></div></div>
      <div class="methods-box" id="m-trend">
        <strong>Daily mention counts:</strong> Shows the top 5 most-mentioned contraceptive types over time, aggregated across all 8 subreddits (or filtered by one). Each data point is the number of unique posts from that day containing a regex match for that type. Days with zero posts are not shown. The time and subreddit filters control the data displayed.
      </div>
      <div class="chart-container"><canvas id="trendChart"></canvas></div>
    </div>
    <div class="card full">
      <div class="card-header"><h2>Side Effect Heatmap</h2><div><button class="methods-btn" onclick="toggleMethods('m-heatmap')">Methods</button><button class="validate-btn" onclick="toggleValidate('v-heatmap','effects')">Validate</button></div></div>
      <div class="methods-box" id="m-heatmap">
        <strong>Contraceptive &times; side-effect matrix:</strong> Data is sourced from <strong>8 subreddits</strong>. Each cell shows the number of posts and comments that mention <strong>both</strong> a contraceptive type and a side effect. Side effects are detected using 24 regex patterns matching symptoms like "bleeding," "cramping," "weight gain," "anxiety," etc. Color intensity scales linearly from transparent (0) to red (max value in the table). <strong>Limitation:</strong> A post saying "I'm worried about weight gain" and one saying "I had no weight gain" both count &mdash; the regex detects the mention, not the context. Top 12 contraceptives and top 15 side effects are shown.
      </div>
      <div class="validate-box" id="v-heatmap"></div>
      <div class="heatmap" id="heatmap"></div>
    </div>
    <div class="card">
      <div class="card-header"><h2>Top Side Effects / Worries</h2><div><button class="methods-btn" onclick="toggleMethods('m-effects')">Methods</button><button class="validate-btn" onclick="toggleValidate('v-effects','effects')">Validate</button></div></div>
      <div class="methods-box" id="m-effects">
        <strong>Ranked side-effect mentions:</strong> Counts the number of unique posts and comments (across all 8 subreddits) that match each of the 24 side-effect regex patterns. A single post mentioning "cramps" and "bleeding" counts once for each category. Patterns include variations (e.g., "headache" and "migraine" both map to "Headaches"). This tracks what <strong>people are talking about</strong>, not necessarily what they experienced &mdash; questions, fears, and reports all count equally.
      </div>
      <div class="validate-box" id="v-effects"></div>
      <div id="effectsList"></div>
    </div>
    <div class="card">
      <div class="card-header"><h2>Category Breakdown</h2><div><button class="methods-btn" onclick="toggleMethods('m-category')">Methods</button></div></div>
      <div class="methods-box" id="m-category">
        <strong>Grouped contraceptive categories:</strong> The 26 individual types are grouped into 6 categories: <strong>IUDs</strong> (Mirena, Kyleena, Liletta, Skyla, Paragard, IUD general), <strong>Pills</strong> (Combined, Mini, general, Slynd, Yaz, Lo Loestrin, Ortho Tri-Cyclen, Junel, Seasonique, Sprintec), <strong>Long-acting</strong> (Nexplanon, Depo-Provera), <strong>Barrier/Other</strong> (Condoms, NuvaRing, patch, spermicide, diaphragm, Phexxi), <strong>Emergency</strong> (Plan B), <strong>Behavioral</strong> (FAM/NFP, withdrawal). The chart sums mention counts within each group.
      </div>
      <div class="chart-container"><canvas id="doughnutChart"></canvas></div>
    </div>
    <div class="card full" id="explorerCard">
      <div class="card-header"><h2>Post Explorer</h2><div><button class="methods-btn" onclick="toggleMethods('m-explorer')">Methods</button></div></div>
      <div class="methods-box" id="m-explorer">
        <strong>Browse raw posts and comments:</strong> Select a contraceptive type to see the top posts (sorted by <strong>engagement score</strong>) that mention it. Posts are sourced from all 8 subreddits. Each post shows:
        <ul>
          <li><strong>Subreddit badge</strong> &mdash; cyan pill showing which subreddit the post came from</li>
          <li><strong>Sentiment badge</strong> &mdash; green (+), red (-), or gray (neutral/none), based on the keyword scorer</li>
          <li><strong>Engagement score</strong> &mdash; composite metric: <code>log2(upvotes) + log2(comments) &times; 1.5</code>, weighting discussion higher than votes</li>
          <li><strong>Side-effect pills</strong> &mdash; yellow tags for each side effect detected in that post's text</li>
          <li><strong>View comments</strong> &mdash; expands to show scraped Reddit comments with their own sentiment scores</li>
        </ul>
      </div>
      <div class="explorer-controls">
        <select id="explorerType"></select>
        <button onclick="loadPosts()">Load Posts</button>
      </div>
      <div class="table-wrap" id="explorerTable"><div class="empty">Select a type and click Load Posts</div></div>
    </div>
  </div>
</main>

<script>
// --- Baked-in data ---
const RAW_POSTS = {posts_json};
const RAW_MENTIONS = {mentions_json};
const RAW_EFFECTS = {effects_json};
const RAW_COMMENTS = {comments_json};
const DB_STATS = {stats_json};
const VALIDATION = {validation_json};

const C = ['#7c6ef0','#e06090','#4ade80','#f0a040','#40b0f0','#f06060','#a070e0','#e0c040',
  '#50d0b0','#f080c0','#70a0f0','#c0e050','#f07050','#60d0e0','#d080f0','#a0d060','#e09070',
  '#80b0d0','#d0a0e0','#90e070'];
const CATS = {{
  'IUDs':['Mirena','Kyleena','Liletta','Skyla','Paragard','IUD (general)'],
  'Pills':['Combined pill','Mini pill','The pill (general)','Slynd','Yaz','Lo Loestrin','Ortho Tri-Cyclen','Junel','Seasonique','Sprintec'],
  'Long-acting':['Nexplanon','Depo-Provera'],
  'Barrier/Other':['Condoms','NuvaRing','Xulane patch','Spermicide','Diaphragm','Phexxi'],
  'Emergency':['Plan B'], 'Behavioral':['FAM/NFP','Withdrawal']
}};

// --- Build indexes for fast lookups ---
// mentionsByPost: post_id -> [contraceptive, ...]
const mentionsByPost = {{}};
for (const [pid, ctype] of RAW_MENTIONS) {{
  if (!mentionsByPost[pid]) mentionsByPost[pid] = [];
  mentionsByPost[pid].push(ctype);
}}
// effectsBySource: "post:id" or "comment:id" -> [effect, ...]
const effectsBySource = {{}};
for (const [stype, sid, eff] of RAW_EFFECTS) {{
  const key = stype + ':' + sid;
  if (!effectsBySource[key]) effectsBySource[key] = [];
  effectsBySource[key].push(eff);
}}
// commentsByPost: post_id -> [comment, ...]
const commentsByPost = {{}};
for (const c of RAW_COMMENTS) {{
  if (!commentsByPost[c.post_id]) commentsByPost[c.post_id] = [];
  commentsByPost[c.post_id].push(c);
}}

let doughnutI = null, trendI = null;

function esc(s) {{ const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }}
function sentPill(v) {{
  if (v == null) return '<span class="pill neu">--</span>';
  const cls = v > 0.05 ? 'pos' : v < -0.05 ? 'neg' : 'neu';
  return `<span class="pill ${{cls}}">${{v > 0 ? '+' : ''}}${{v.toFixed(2)}}</span>`;
}}
function sentColor(v) {{ return v > 0.05 ? '#4ade80' : v < -0.05 ? '#f06060' : '#8b90a0'; }}
function heatColor(v, mx) {{
  if (!v) return 'transparent';
  const t = Math.min(v / Math.max(mx, 1), 1);
  const r = Math.round(240 * t + 30 * (1 - t)), g = Math.round(96 * t + 30 * (1 - t)), b = Math.round(96 * t + 60 * (1 - t));
  return `rgba(${{r}},${{g}},${{b}},${{0.3 + t * 0.7}})`;
}}
function stat(label, val, cls, sub) {{
  return `<div class="stat-card"><div class="label">${{label}}</div><div class="value ${{cls}}">${{val}}</div>${{sub ? `<div class="sub">${{sub}}</div>` : ''}}</div>`;
}}

// --- Filtering ---
function getFilter() {{
  const fromStr = document.getElementById('dateFrom').value;
  const toStr = document.getElementById('dateTo').value;
  const subV = document.getElementById('subFilter').value;
  let dateFrom = null, dateTo = null;
  if (fromStr) dateFrom = new Date(fromStr + 'T00:00:00').getTime() / 1000;
  if (toStr) dateTo = new Date(toStr + 'T00:00:00').getTime() / 1000 + 86400;
  return {{ dateFrom, dateTo, sub: subV || null }};
}}

function filterPosts(f) {{
  return RAW_POSTS.filter(p => {{
    if (f.dateFrom != null && p.created_utc < f.dateFrom) return false;
    if (f.dateTo != null && p.created_utc > f.dateTo) return false;
    if (f.sub && p.subreddit !== f.sub) return false;
    return true;
  }});
}}

function computeMentionCounts(posts) {{
  const counts = {{}};
  const postIds = new Set(posts.map(p => p.id));
  for (const [pid, ctype] of RAW_MENTIONS) {{
    if (!postIds.has(pid)) continue;
    counts[ctype] = (counts[ctype] || 0) + 1;
  }}
  return Object.entries(counts).sort((a, b) => b[1] - a[1]);
}}

function computeDailyCounts(posts) {{
  const daily = {{}};
  const postIds = new Set(posts.map(p => p.id));
  for (const [pid, ctype] of RAW_MENTIONS) {{
    if (!postIds.has(pid)) continue;
    const post = RAW_POSTS.find(p => p.id === pid);
    if (!post) continue;
    const day = new Date(post.created_utc * 1000).toISOString().slice(0, 10);
    if (!daily[day]) daily[day] = {{}};
    daily[day][ctype] = (daily[day][ctype] || 0) + 1;
  }}
  return daily;
}}

function computeSentimentByType(posts) {{
  const postIds = new Set(posts.map(p => p.id));
  const acc = {{}};
  for (const [pid, ctype] of RAW_MENTIONS) {{
    if (!postIds.has(pid)) continue;
    const post = RAW_POSTS.find(p => p.id === pid);
    if (!post || post.sentiment == null) continue;
    if (!acc[ctype]) acc[ctype] = {{ sum: 0, cnt: 0 }};
    acc[ctype].sum += post.sentiment;
    acc[ctype].cnt += 1;
  }}
  return Object.entries(acc)
    .filter(([, v]) => v.cnt >= 2)
    .map(([name, v]) => [name, Math.round((v.sum / v.cnt) * 1000) / 1000, v.cnt])
    .sort((a, b) => b[1] - a[1]);
}}

function computeSideEffectCounts(posts) {{
  const postIds = new Set(posts.map(p => p.id));
  const counts = {{}};
  for (const [stype, sid, eff] of RAW_EFFECTS) {{
    if (stype === 'post' && postIds.has(sid)) {{
      counts[eff] = (counts[eff] || 0) + 1;
    }} else if (stype === 'comment') {{
      const c = RAW_COMMENTS.find(cm => cm.id === sid);
      if (c && postIds.has(c.post_id)) {{
        counts[eff] = (counts[eff] || 0) + 1;
      }}
    }}
  }}
  return Object.entries(counts).sort((a, b) => b[1] - a[1]);
}}

function computeHeatmap(posts) {{
  const postIds = new Set(posts.map(p => p.id));
  const result = {{}};
  // Post-level: contraceptive from mentions, effect from side_effects
  for (const [pid, ctype] of RAW_MENTIONS) {{
    if (!postIds.has(pid)) continue;
    const effs = effectsBySource['post:' + pid] || [];
    for (const eff of effs) {{
      if (!result[ctype]) result[ctype] = {{}};
      result[ctype][eff] = (result[ctype][eff] || 0) + 1;
    }}
  }}
  // Comment-level
  for (const c of RAW_COMMENTS) {{
    if (!postIds.has(c.post_id)) continue;
    const cMentions = mentionsByPost[c.post_id] || [];
    const cEffects = effectsBySource['comment:' + c.id] || [];
    for (const ctype of cMentions) {{
      for (const eff of cEffects) {{
        if (!result[ctype]) result[ctype] = {{}};
        result[ctype][eff] = (result[ctype][eff] || 0) + 1;
      }}
    }}
  }}
  return result;
}}

// --- Presets & state ---
function setPreset(n) {{
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  if (n > 0) {{
    const to = new Date(), from = new Date();
    from.setDate(from.getDate() - n);
    document.getElementById('dateFrom').value = from.toISOString().slice(0, 10);
    document.getElementById('dateTo').value = to.toISOString().slice(0, 10);
    const btn = document.getElementById('pre' + n);
    if (btn) btn.classList.add('active');
  }} else {{
    document.getElementById('dateFrom').value = '';
    document.getElementById('dateTo').value = '';
    document.getElementById('pre0').classList.add('active');
  }}
  saveState();
  renderAll();
}}

function saveState() {{
  const f = document.getElementById('dateFrom').value;
  const t = document.getElementById('dateTo').value;
  const s = document.getElementById('subFilter').value;
  const parts = [];
  if (f) parts.push('from=' + f);
  if (t) parts.push('to=' + t);
  if (s) parts.push('sub=' + s);
  history.replaceState(null, '', parts.length ? '#' + parts.join('&') : '#');
}}

function loadState() {{
  const h = window.location.hash.slice(1);
  if (!h) return false;
  const p = new URLSearchParams(h);
  if (p.get('from')) document.getElementById('dateFrom').value = p.get('from');
  if (p.get('to')) document.getElementById('dateTo').value = p.get('to');
  if (p.get('sub')) document.getElementById('subFilter').value = p.get('sub');
  highlightPreset();
  return true;
}}

function highlightPreset() {{
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  const f = document.getElementById('dateFrom').value;
  const t = document.getElementById('dateTo').value;
  if (!f && !t) {{ document.getElementById('pre0').classList.add('active'); return; }}
  const today = new Date().toISOString().slice(0, 10);
  if (t !== today) return;
  for (const n of [7, 30, 90]) {{
    const d = new Date(); d.setDate(d.getDate() - n);
    if (f === d.toISOString().slice(0, 10)) {{ document.getElementById('pre' + n).classList.add('active'); return; }}
  }}
}}

function exportCSV() {{
  const f = getFilter();
  const posts = filterPosts(f);
  const mc = computeMentionCounts(posts);
  if (!mc.length) {{ alert('No data to export.'); return; }}
  const sentArr = computeSentimentByType(posts);
  const sentMap = Object.fromEntries(sentArr.map(([n, avg, cnt]) => [n, {{ avg, cnt }}]));
  let csv = 'Contraceptive,Mentions,Avg Sentiment,Post Count\\n';
  for (const [name, count] of mc) {{
    const s = sentMap[name] || {{ avg: null, cnt: '' }};
    csv += '"' + name + '",' + count + ',' + (s.avg != null ? s.avg.toFixed(3) : '') + ',' + (s.cnt || '') + '\\n';
  }}
  const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'contraceptive-tracker-' + new Date().toISOString().slice(0, 10) + '.csv';
  a.click();
  URL.revokeObjectURL(a.href);
}}

// --- Main render ---
function renderAll() {{
  const f = getFilter();
  const posts = filterPosts(f);
  const mc = computeMentionCounts(posts);
  const daily = computeDailyCounts(posts);
  const sentData = computeSentimentByType(posts);
  const effectsData = computeSideEffectCounts(posts);
  const heatData = computeHeatmap(posts);

  const totalM = mc.reduce((s, e) => s + e[1], 0);
  const avgSent = DB_STATS.avg_sentiment;
  const sentStr = avgSent != null ? (avgSent > 0 ? '+' : '') + avgSent.toFixed(2) : '--';
  const sentCls = avgSent > 0.05 ? 'green' : avgSent < -0.05 ? 'red' : 'yellow';

  document.getElementById('statsRow').innerHTML = [
    stat('Posts', DB_STATS.total_posts || 0, 'accent', `${{DB_STATS.total_scrapes || 0}} scrapes`),
    stat('Comments', DB_STATS.total_comments || 0, 'cyan'),
    stat('Mentions (filtered)', totalM, 'accent2'),
    stat('Avg Sentiment', sentStr, sentCls),
    stat('Subreddits', DB_STATS.subreddit_count || 0, 'green'),
    stat('Types', mc.length, ''),
  ].join('');

  // Bar chart
  const mx = mc.length ? mc[0][1] : 1;
  document.getElementById('barChart').innerHTML = mc.length ? mc.map(([n, cnt], i) => {{
    const p = (cnt / mx * 100).toFixed(1);
    return `<div class="bar-row"><div class="bar-label">${{n}}</div><div class="bar-track"><div class="bar-fill" style="width:${{p}}%;background:${{C[i % C.length]}}"></div></div><div class="bar-count">${{cnt}}</div></div>`;
  }}).join('') : '<div class="empty">No data</div>';

  // Sentiment chart
  document.getElementById('sentChart').innerHTML = sentData.length ? sentData.map(([n, avg, cnt]) => {{
    const col = sentColor(avg);
    return `<div class="bar-row"><div class="bar-label">${{n}}</div>
      <div class="sent-bar"><div class="sent-track"><div class="sent-fill" style="left:50%;width:${{Math.abs(avg) * 50}}%;${{avg < 0 ? 'right:50%;left:auto;' : ''}}background:${{col}}"></div></div>
      <div class="sent-val" style="color:${{col}}">${{avg > 0 ? '+' : ''}}${{avg.toFixed(2)}}</div></div>
      <div class="bar-count" title="${{cnt}} posts">${{cnt}}p</div></div>`;
  }}).join('') : '<div class="empty">No sentiment data</div>';

  // Explorer dropdown
  const sel = document.getElementById('explorerType');
  const prev = sel.value;
  sel.innerHTML = mc.map(([n]) => `<option value="${{n}}">${{n}}</option>`).join('');
  if (prev) sel.value = prev;

  // Doughnut
  const tots = Object.fromEntries(mc);
  const catT = {{}};
  for (const [cat, ms] of Object.entries(CATS)) catT[cat] = ms.reduce((s, m) => s + (tots[m] || 0), 0);
  const ce = Object.entries(catT).filter(e => e[1] > 0).sort((a, b) => b[1] - a[1]);
  if (doughnutI) doughnutI.destroy();
  doughnutI = new Chart(document.getElementById('doughnutChart'), {{
    type: 'doughnut', data: {{ labels: ce.map(e => e[0]), datasets: [{{ data: ce.map(e => e[1]), backgroundColor: C.slice(0, ce.length), borderWidth: 0 }}] }},
    options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'right', labels: {{ color: '#e1e4ed', padding: 10, font: {{ size: 11 }} }} }} }} }}
  }});

  // Trend
  const dates = Object.keys(daily).sort();
  const top5 = mc.slice(0, 5).map(e => e[0]);
  const ds = top5.map((n, i) => ({{ label: n, data: dates.map(d => (daily[d] || {{}})[n] || 0), borderColor: C[i], backgroundColor: C[i] + '22', tension: 0.3, fill: false, pointRadius: 2 }}));
  if (trendI) trendI.destroy();
  trendI = new Chart(document.getElementById('trendChart'), {{
    type: 'line', data: {{ labels: dates, datasets: ds }},
    options: {{ responsive: true, maintainAspectRatio: false,
      scales: {{ x: {{ ticks: {{ color: '#8b90a0' }}, grid: {{ color: '#2a2d3a' }} }}, y: {{ beginAtZero: true, ticks: {{ color: '#8b90a0' }}, grid: {{ color: '#2a2d3a' }} }} }},
      plugins: {{ legend: {{ labels: {{ color: '#e1e4ed', padding: 10, font: {{ size: 11 }} }} }} }} }}
  }});

  // Side effects list
  document.getElementById('effectsList').innerHTML = effectsData.length ?
    effectsData.slice(0, 15).map(([eff, cnt], i) => {{
      const p = (cnt / (effectsData[0][1] || 1) * 100).toFixed(1);
      return `<div class="bar-row"><div class="bar-label">${{eff}}</div><div class="bar-track"><div class="bar-fill" style="width:${{p}}%;background:${{C[(i + 5) % C.length]}}"></div></div><div class="bar-count">${{cnt}}</div></div>`;
    }}).join('') : '<div class="empty">No side-effect data yet</div>';

  // Heatmap
  renderHeatmap(heatData);
}}

function renderHeatmap(heatData) {{
  const types = Object.keys(heatData);
  if (!types.length) {{ document.getElementById('heatmap').innerHTML = '<div class="empty">No data yet</div>'; return; }}
  const allE = new Set();
  for (const effs of Object.values(heatData)) for (const e of Object.keys(effs)) allE.add(e);
  const effTotals = {{}};
  for (const e of allE) {{ effTotals[e] = 0; for (const t of types) effTotals[e] += (heatData[t][e] || 0); }}
  const sortedE = Array.from(allE).sort((a, b) => effTotals[b] - effTotals[a]).slice(0, 15);
  const typeTotals = {{}};
  for (const t of types) {{ typeTotals[t] = 0; for (const e of sortedE) typeTotals[t] += (heatData[t][e] || 0); }}
  const sortedT = types.sort((a, b) => typeTotals[b] - typeTotals[a]).slice(0, 12);
  let mx = 0;
  for (const t of sortedT) for (const e of sortedE) mx = Math.max(mx, heatData[t][e] || 0);

  let h = '<table><thead><tr><th></th>';
  for (const e of sortedE) h += `<th style="writing-mode:vertical-lr;transform:rotate(180deg);max-width:20px">${{e}}</th>`;
  h += '</tr></thead><tbody>';
  for (const t of sortedT) {{
    h += `<tr><td class="row-label">${{t}}</td>`;
    for (const e of sortedE) {{
      const v = heatData[t]?.[e] || 0;
      h += `<td><span class="heat-cell" style="background:${{heatColor(v, mx)}}">${{v || ''}}</span></td>`;
    }}
    h += '</tr>';
  }}
  h += '</tbody></table>';
  document.getElementById('heatmap').innerHTML = h;
}}

// --- Post Explorer (client-side) ---
function loadPosts() {{
  const type = document.getElementById('explorerType').value;
  if (!type) return;
  const el = document.getElementById('explorerTable');
  const f = getFilter();
  const posts = filterPosts(f);
  const postIds = new Set(posts.map(p => p.id));

  // Find posts that mention this type
  const matchedIds = new Set();
  for (const [pid, ctype] of RAW_MENTIONS) {{
    if (ctype === type && postIds.has(pid)) matchedIds.add(pid);
  }}

  // Get full post objects, sorted by engagement
  const matchedPosts = RAW_POSTS
    .filter(p => matchedIds.has(p.id))
    .sort((a, b) => (b.engagement_score || 0) - (a.engagement_score || 0))
    .slice(0, 30);

  if (!matchedPosts.length) {{ el.innerHTML = '<div class="empty">No posts</div>'; return; }}

  let h = '<table><thead><tr><th>Post</th><th>Sentiment</th><th>Engage</th><th>Score</th><th>Comments</th><th>Date</th></tr></thead><tbody>';
  for (const p of matchedPosts) {{
    const link = p.permalink ? 'https://www.reddit.com' + p.permalink : '#';
    const title = esc(p.title || '(no title)');
    const text = esc((p.selftext || '').slice(0, 400));
    const date = p.created_utc ? new Date(p.created_utc * 1000).toLocaleDateString() : '';
    const id = 'p-' + p.id;
    const subBadge = p.subreddit ? `<span class="pill" style="border-color:var(--cyan);color:var(--cyan)">r/${{esc(p.subreddit)}}</span>` : '';
    const engScore = p.engagement_score != null ? p.engagement_score.toFixed(1) : '--';
    const effs = effectsBySource['post:' + p.id] || [];
    const effPills = effs.map(e => `<span class="pill effect">${{e}}</span>`).join('');
    h += `<tr><td>
      <a class="post-link" href="${{link}}" target="_blank" rel="noopener">${{title}}</a> ${{subBadge}}
      ${{effPills ? `<div style="margin-top:2px">${{effPills}}</div>` : ''}}
      ${{text ? `<div class="post-text" id="${{id}}">${{text}}</div><span class="toggle-text" onclick="toggleText('${{id}}')">show more</span>` : ''}}
      <div id="cmt-${{p.id}}"></div>
      <span class="toggle-text" onclick="toggleComments('${{p.id}}')">view comments</span>
    </td><td>${{sentPill(p.sentiment)}}</td><td>${{engScore}}</td><td>${{p.score}}</td><td>${{p.num_comments}}</td><td>${{date}}</td></tr>`;
  }}
  h += '</tbody></table>';
  el.innerHTML = h;
}}

function toggleText(id) {{ const el = document.getElementById(id); if (el) el.classList.toggle('expanded'); }}

function toggleComments(postId) {{
  const el = document.getElementById('cmt-' + postId);
  if (el.innerHTML) {{ el.innerHTML = ''; return; }}
  const cmts = commentsByPost[postId] || [];
  if (!cmts.length) {{ el.innerHTML = '<div class="comments-section">No comments scraped yet</div>'; return; }}
  let h = '<div class="comments-section">';
  for (const c of cmts.slice(0, 20)) {{
    const body = esc(c.body || '').slice(0, 300);
    h += `<div class="comment-item"><div>${{body}}</div><div class="comment-meta">u/${{esc(c.author || '?')}} | score: ${{c.score}} ${{sentPill(c.sentiment)}}</div></div>`;
  }}
  if (cmts.length > 20) h += `<div class="comment-meta" style="padding:.5rem 0">...and ${{cmts.length - 20}} more</div>`;
  h += '</div>';
  el.innerHTML = h;
}}

// --- Methods & Validate toggles ---
function toggleMethods(id) {{
  const box = document.getElementById(id);
  box.classList.toggle('visible');
  const header = box.closest('.card').querySelector('.methods-btn');
  if (header) header.classList.toggle('active');
}}

function toggleValidate(id, section) {{
  const box = document.getElementById(id);
  const card = box.closest('.card');
  const btn = card.querySelector('.validate-btn');

  if (box.classList.contains('visible')) {{
    box.classList.remove('visible');
    if (btn) btn.classList.remove('active');
    return;
  }}

  box.classList.add('visible');
  if (btn) btn.classList.add('active');

  const examples = VALIDATION[section] || [];
  if (!examples.length) {{ box.innerHTML = '<div class="empty" style="padding:.5rem">No examples available yet. Run a scrape first.</div>'; return; }}

  if (section === 'sentiment') box.innerHTML = renderSentimentValidation(examples);
  else if (section === 'mentions') box.innerHTML = renderMentionValidation(examples);
  else box.innerHTML = renderEffectsValidation(examples);
}}

function renderSentimentValidation(examples) {{
  let h = '<div style="margin-bottom:.5rem;font-size:.75rem;color:var(--muted)"><strong style="color:var(--text)">Validation:</strong> Real posts analyzed step-by-step. Words are highlighted: <span class="hl-pos">positive</span> <span class="hl-neg">negative</span> <span class="hl-negator">negator</span> <span class="hl-intensifier">intensifier</span></div>';
  for (const ex of examples) {{
    h += '<div class="val-example">';
    h += `<div class="val-title">${{esc(ex.title)}}</div>`;
    const bd = ex.breakdown;
    if (bd && bd.steps && bd.steps.length) {{
      h += '<div class="val-steps"><table>';
      h += '<tr><th>Word</th><th>Role</th><th>Effect</th><th>Running +/-</th></tr>';
      for (const s of bd.steps) {{
        const cls = s.role.includes('positive') ? 'hl-pos' : s.role.includes('negative') ? 'hl-neg' : s.role === 'negator' ? 'hl-negator' : s.role === 'intensifier' ? 'hl-intensifier' : '';
        const running = (s.running_pos != null) ? `+${{s.running_pos}} / -${{s.running_neg}}` : '';
        h += `<tr><td><span class="${{cls}}">${{s.word}}</span></td><td>${{s.role}}</td><td>${{s.effect}}</td><td>${{running}}</td></tr>`;
      }}
      h += '</table></div>';
    }}
    if (bd) h += `<div class="val-summary" style="color:${{sentColor(bd.score || 0)}}">${{bd.summary}}</div>`;
    h += '</div>';
  }}
  return h;
}}

function renderMentionValidation(examples) {{
  let h = '<div style="margin-bottom:.5rem;font-size:.75rem;color:var(--muted)"><strong style="color:var(--text)">Validation:</strong> Real posts showing exact regex matches. <span class="hl-mention">Matched text</span> is highlighted with the detected type.</div>';
  for (const ex of examples) {{
    h += '<div class="val-example">';
    h += `<div class="val-title">${{esc(ex.title)}}</div>`;
    if (ex.matches && ex.matches.length) {{
      h += '<div style="margin:.3rem 0">';
      for (const m of ex.matches) {{
        h += `<span class="pill" style="border-color:var(--accent);color:var(--accent)">${{m.name}}: "${{esc(m.matched)}}"</span> `;
      }}
      h += '</div>';
      h += `<div class="val-text">${{esc((ex.text_preview || '').slice(0, 250))}}</div>`;
    }}
    h += '</div>';
  }}
  return h;
}}

function renderEffectsValidation(examples) {{
  let h = '<div style="margin-bottom:.5rem;font-size:.75rem;color:var(--muted)"><strong style="color:var(--text)">Validation:</strong> Real posts showing detected side effects and contraceptive matches.</div>';
  for (const ex of examples) {{
    h += '<div class="val-example">';
    h += `<div class="val-title">${{esc(ex.title)}}</div>`;
    if (ex.mention_matches && ex.mention_matches.length) {{
      h += '<div style="margin:.2rem 0"><strong style="font-size:.7rem;color:var(--muted)">Contraceptives:</strong> ';
      for (const m of ex.mention_matches) h += `<span class="pill" style="border-color:var(--accent);color:var(--accent)">${{m.name}}: "${{esc(m.matched)}}"</span> `;
      h += '</div>';
    }}
    if (ex.side_effect_matches && ex.side_effect_matches.length) {{
      h += '<div style="margin:.2rem 0"><strong style="font-size:.7rem;color:var(--muted)">Side effects:</strong> ';
      for (const m of ex.side_effect_matches) h += `<span class="pill effect">${{m.name}}: "${{esc(m.matched)}}"</span> `;
      h += '</div>';
    }}
    h += `<div class="val-text">${{esc((ex.text_preview || '').slice(0, 250))}}</div>`;
    h += '</div>';
  }}
  return h;
}}

// --- Event listeners ---
document.getElementById('dateFrom').addEventListener('change', () => {{ highlightPreset(); saveState(); renderAll(); }});
document.getElementById('dateTo').addEventListener('change', () => {{ highlightPreset(); saveState(); renderAll(); }});
document.getElementById('subFilter').addEventListener('change', () => {{ saveState(); renderAll(); }});
window.addEventListener('hashchange', () => {{ loadState(); renderAll(); }});

if (!loadState()) setPreset(0); else renderAll();
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate static dashboard site")
    parser.add_argument("--push", action="store_true",
                        help="After generating, git add + commit + push")
    args = parser.parse_args()

    conn = tracker.get_db()
    tracker.migrate_legacy_json(conn)
    tracker.backfill_sentiment_and_effects(conn)

    print("Exporting data from database...")
    data = tracker.export_all_data(conn)
    conn.close()

    print(f"  {len(data['posts'])} posts, {len(data['mentions'])} mentions, "
          f"{len(data['side_effects'])} effects, {len(data['comments'])} comments")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    html = generate_html(data)
    out_path = DOCS_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"Generated {out_path} ({size_kb:.0f} KB)")

    if args.push:
        project_dir = Path(__file__).parent
        try:
            subprocess.run(
                ["git", "add", "docs/index.html"],
                cwd=str(project_dir), check=True, capture_output=True,
            )
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=str(project_dir), capture_output=True,
            )
            if result.returncode != 0:
                subprocess.run(
                    ["git", "commit", "-m", "Update dashboard data"],
                    cwd=str(project_dir), check=True, capture_output=True,
                )
                subprocess.run(
                    ["git", "push"],
                    cwd=str(project_dir), check=True, capture_output=True,
                )
                print("Pushed to GitHub.")
            else:
                print("No changes to push.")
        except subprocess.CalledProcessError as e:
            print(f"Git push failed: {e.stderr.decode() if e.stderr else e}")
        except FileNotFoundError:
            print("Git not found. Skipping push.")


if __name__ == "__main__":
    main()
