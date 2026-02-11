#!/usr/bin/env python3
"""
Contraceptive Mention Tracker — Multi-Subreddit

Scrapes 8 subreddits for contraceptive discussions, stores everything in
SQLite, runs sentiment analysis, and tracks side-effect mentions.

Usage:
    python bc_tracker.py scrape          # Scrape today's posts + comments
    python bc_tracker.py scrape --all    # Include all fetched posts
    python bc_tracker.py report          # Print summary report
    python bc_tracker.py report --days 7 # Report for last 7 days
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import shutil
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "bc_tracker_data"
DB_FILE = DATA_DIR / "tracker.db"
LEGACY_JSON = DATA_DIR / "daily_mentions.json"
BACKUP_DIR = Path.home() / "Library" / "CloudStorage" / "Dropbox-Personal" / "backups" / "reddit-bc-tracker"
LOG_FILE = DATA_DIR / "scrape_errors.log"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("bc_tracker")
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                       datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(ch)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(str(LOG_FILE))
    fh.setLevel(logging.WARNING)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                       datefmt="%Y-%m-%d %H:%M:%S"))
    logger.addHandler(fh)
    return logger

log = _setup_logging()

# ---------------------------------------------------------------------------
# Subreddit configuration
# ---------------------------------------------------------------------------

SUBREDDITS = [
    {"name": "birthcontrol",    "limit": 200},
    {"name": "TwoXChromosomes", "limit": 100},
    {"name": "abortion",        "limit": 100},
    {"name": "prochoice",       "limit": 100},
    {"name": "prolife",         "limit": 100},
    {"name": "sex",             "limit": 100},
    {"name": "AskDocs",         "limit": 100},
    {"name": "WomensHealth",    "limit": 100},
]

# ---------------------------------------------------------------------------
# Contraceptive patterns
# ---------------------------------------------------------------------------

CONTRACEPTIVES = {
    "Mirena": r"\bmir[ei]na\b|\bmer[ei]na\b",
    "Kyleena": r"\bkyleena\b|\bkylena\b",
    "Liletta": r"\bliletta\b|\blilletta\b",
    "Skyla": r"\bskyla\b|\bskila\b",
    "Paragard": r"\bparagard\b|\bparaguard\b|\bpara\s*guard\b|\bcopper\s*iud\b|\bcopper\s*t\b",
    "IUD (general)": r"\biud\b(?!.*(?:mirena|kyleena|paragard|liletta|skyla))|\bhormonal\s+iud\b",
    "Nexplanon": r"\bnexplanon\b|\bnexplanion\b|\bimplanon\b|\bthe\s+implant\b|\barm\s+implant\b|\bimplant\s+in\s+(?:my\s+)?arm\b",
    "Combined pill": r"\bcombined\s+pill\b|\bcombination\s+pill\b|\bcoc\b",
    "Mini pill": r"\bmini[\s-]*pill\b|\bpop\b(?:\s+pill)?|\bprogestin[\s-]+only\s+pill\b",
    "The pill (general)": r"\b(?:the|birth\s*control|bc)\s+pill[s]?\b|\boral\s+contracepti\w+\b|\bbc\s+pills?\b",
    "Depo-Provera": r"\bdepo\b|\bthe\s+shot\b|\bdepo[\s-]*provera\b|\bbirth\s*control\s+shot\b|\bbc\s+shot\b",
    "NuvaRing": r"\bnuvaring\b|\bnuva\s+ring\b|\bthe\s+ring\b|\bannovera\b",
    "Xulane patch": r"\bxulane\b|\bthe\s+patch\b|\bortho\s*evra\b|\btwirla\b|\bbc\s+patch\b|\bbirth\s*control\s+patch\b",
    "Plan B": r"\bplan\s*b\b|\bmorning[\s-]+after\b|\bemergency\s+contracep\w+\b|\bella\b|\bec\s+pill\b",
    "Condoms": r"\bcondom[s]?\b",
    "Spermicide": r"\bspermicid\w+\b",
    "Diaphragm": r"\bdiaphragm\b|\bcaya\b",
    "FAM/NFP": r"\bfam\b|\bnfp\b|\bfertility\s+awareness\b|\bnatural\s+family\s+planning\b|\btemping\b|\bbbt\b|\bbasal\s+body\s+temp\b",
    "Withdrawal": r"\bwithdrawal\b|\bpull\s*(?:ing\s+)?out\b|\bpull\s+out\s+method\b",
    "Slynd": r"\bslynd\b",
    "Yaz": r"\byaz\b|\byasmin\b|\byasmine\b",
    "Lo Loestrin": r"\blo\s*loestrin\b|\blo\s*lo\b",
    "Phexxi": r"\bphexxi\b",
    "Ortho Tri-Cyclen": r"\bortho[\s-]*tri[\s-]*cyclen\b|\btri[\s-]*sprintec\b|\btri[\s-]*lo[\s-]*sprintec\b",
    "Junel": r"\bjunel\b|\bjunel\s+fe\b|\bloestrin\b(?!\s*lo)|\bmicrogestin\b",
    "Seasonique": r"\bseasonique\b|\bseasonale\b|\bjolessa\b|\bcamrese\b",
    "Sprintec": r"\bsprintec\b(?!\s*tri)|\bmono[\s-]*linyah\b",
}

_COMPILED_CONTRA = {name: re.compile(pat, re.IGNORECASE) for name, pat in CONTRACEPTIVES.items()}

# ---------------------------------------------------------------------------
# Side-effect patterns
# ---------------------------------------------------------------------------

SIDE_EFFECTS = {
    "Bleeding/spotting": r"\bbleed(?:ing)?\b|\bspotting\b|\bheavy\s+period\b|\birregular\s+bleed",
    "Cramping": r"\bcramp(?:s|ing)?\b",
    "Weight gain": r"\bweight\s+gain\b|\bgained\s+weight\b|\bgaining\s+weight\b",
    "Weight loss": r"\bweight\s+loss\b|\blos(?:t|ing)\s+weight\b",
    "Acne": r"\bacne\b|\bbreakout[s]?\b|\bpimple[s]?\b|\bzit[s]?\b",
    "Hair loss": r"\bhair\s+(?:loss|thin(?:ning)?|fall(?:ing)?)\b|\bshedding\s+hair\b|\blosing\s+hair\b",
    "Mood swings": r"\bmood\s+swing[s]?\b|\bmood\s+change[s]?\b|\bemotional\b|\birritable\b|\birritab(?:le|ility)\b",
    "Depression": r"\bdepress(?:ed|ion|ing)?\b|\bmental\s+health\b|\bsuicidal\b",
    "Anxiety": r"\banxi(?:ety|ous)\b|\bpanic\s+attack[s]?\b|\bnervous(?:ness)?\b",
    "Headaches": r"\bheadache[s]?\b|\bmigraine[s]?\b",
    "Nausea": r"\bnause(?:a|ous|ated)\b|\bvomit(?:ing)?\b|\bthrew\s+up\b|\bthrow(?:ing)?\s+up\b",
    "Fatigue": r"\bfatigue[d]?\b|\bexhaust(?:ed|ion)\b|\btired(?:ness)?\b|\blethargi?c\b|\bno\s+energy\b",
    "Low libido": r"\blow\s+libido\b|\bno\s+(?:sex\s+)?drive\b|\blibido\b|\bsex\s+drive\b",
    "Breast tenderness": r"\bbreast\s+(?:tender(?:ness)?|sore(?:ness)?|pain)\b|\bsore\s+breast[s]?\b|\bsore\s+boob[s]?\b",
    "Bloating": r"\bbloat(?:ed|ing)?\b",
    "Back pain": r"\bback\s+pain\b|\blower\s+back\b",
    "Insertion pain": r"\binsertion\s+(?:pain|hurt|awful|terrible)\b|\bpain(?:ful)?\s+insertion\b",
    "Removal pain": r"\bremoval\s+(?:pain|hurt)\b|\bpain(?:ful)?\s+removal\b",
    "Infection": r"\binfection[s]?\b|\bbv\b|\byeast\s+infection\b|\bbacterial\s+vaginosis\b|\buti\b",
    "Strings": r"\bstring[s]?\b|\bcan'?t\s+feel\b|\bpartner\s+(?:feel|felt)\b",
    "Expulsion": r"\bexpuls(?:ion|ed)\b|\bfell\s+out\b|\bcame\s+out\b|\bdisplaced\b|\bmoved\b",
    "Blood clots": r"\bblood\s+clot[s]?\b|\bdvt\b|\bthrombos[ie]s\b|\bpulmonary\s+embolism\b|\bpe\b",
    "Brain fog": r"\bbrain\s+fog\b|\bfog(?:gy|giness)\b|\bcan'?t\s+(?:think|concentrate|focus)\b",
    "Dizziness": r"\bdizz(?:y|iness)\b|\blightheaded\b|\bfaint(?:ing|ed)?\b",
}

_COMPILED_EFFECTS = {name: re.compile(pat, re.IGNORECASE) for name, pat in SIDE_EFFECTS.items()}

# ---------------------------------------------------------------------------
# Sentiment analysis (keyword-based, no external deps)
# ---------------------------------------------------------------------------

_POSITIVE_WORDS = {
    "love", "loved", "loving", "great", "amazing", "wonderful", "fantastic",
    "happy", "happier", "recommend", "recommended", "perfect", "relief",
    "comfortable", "easy", "easier", "helped", "helping", "works", "worked",
    "effective", "glad", "satisfied", "awesome", "excellent", "best", "better",
    "worth", "grateful", "thankful", "thrilled", "pleased", "enjoy", "enjoying",
    "improvement", "improved", "freedom", "convenient", "reliable", "safe",
    "success", "successful", "smooth", "positive", "hopeful", "reassuring",
}

_NEGATIVE_WORDS = {
    "hate", "hated", "hating", "terrible", "awful", "horrible", "worst",
    "pain", "painful", "suffering", "miserable", "nightmare", "regret",
    "regretted", "angry", "frustrated", "frustrating", "unbearable",
    "ruined", "scared", "scary", "fear", "worried", "worry", "worrying",
    "concerned", "bad", "worse", "sucks", "sucked", "annoying", "annoyed",
    "disappointing", "disappointed", "uncomfortable", "difficult", "hard",
    "struggle", "struggling", "failed", "failure", "problem", "problems",
    "issue", "issues", "wrong", "severe", "seriously", "misery", "cry",
    "crying", "cried", "upset", "distressed", "suffering", "hurt", "hurts",
}

_INTENSIFIERS = {"very", "really", "extremely", "so", "incredibly", "super", "absolutely", "totally"}
_NEGATORS = {"not", "no", "never", "don't", "didn't", "doesn't", "wasn't", "weren't", "isn't", "aren't", "won't", "can't", "couldn't", "shouldn't", "hardly", "barely"}


def score_sentiment(text: str) -> Optional[float]:
    """
    Score text sentiment from -1.0 (very negative) to +1.0 (very positive).
    Returns None if no sentiment words found.
    """
    if not text:
        return None
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return None

    pos_score = 0.0
    neg_score = 0.0
    negate = False
    intensify = 1.0

    for word in words:
        if word in _NEGATORS:
            negate = True
            continue
        if word in _INTENSIFIERS:
            intensify = 1.5
            continue

        if word in _POSITIVE_WORDS:
            if negate:
                neg_score += intensify
            else:
                pos_score += intensify
            negate = False
            intensify = 1.0
        elif word in _NEGATIVE_WORDS:
            if negate:
                pos_score += intensify
            else:
                neg_score += intensify
            negate = False
            intensify = 1.0
        else:
            # Reset modifiers after non-sentiment word
            if word not in _INTENSIFIERS and word not in _NEGATORS:
                negate = False
                intensify = 1.0

    total = pos_score + neg_score
    if total == 0:
        return None
    raw = (pos_score - neg_score) / total
    return max(-1.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def find_mentions(text: str) -> list:
    return [name for name, pat in _COMPILED_CONTRA.items() if pat.search(text)]


def find_side_effects(text: str) -> list:
    return [name for name, pat in _COMPILED_EFFECTS.items() if pat.search(text)]


# ---------------------------------------------------------------------------
# Explain / validate functions — show HOW the analysis worked on real text
# ---------------------------------------------------------------------------

def explain_mentions(text: str) -> list:
    """Return [{name, matched_text, start, end}] for each contraceptive found."""
    results = []
    for name, pat in _COMPILED_CONTRA.items():
        for m in pat.finditer(text):
            results.append({
                "name": name,
                "matched": m.group(),
                "start": m.start(),
                "end": m.end(),
            })
    results.sort(key=lambda r: r["start"])
    return results


def explain_side_effects(text: str) -> list:
    """Return [{name, matched_text, start, end}] for each side effect found."""
    results = []
    for name, pat in _COMPILED_EFFECTS.items():
        for m in pat.finditer(text):
            results.append({
                "name": name,
                "matched": m.group(),
                "start": m.start(),
                "end": m.end(),
            })
    results.sort(key=lambda r: r["start"])
    return results


def explain_sentiment(text: str) -> dict:
    """
    Return a step-by-step breakdown of how sentiment was scored.
    Includes each word's role and the running calculation.
    """
    if not text:
        return {"score": None, "steps": [], "summary": "Empty text."}

    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return {"score": None, "steps": [], "summary": "No words found."}

    steps = []
    pos_score = 0.0
    neg_score = 0.0
    negate = False
    intensify = 1.0

    for word in words:
        if word in _NEGATORS:
            negate = True
            steps.append({"word": word, "role": "negator", "effect": "flips next word"})
            continue
        if word in _INTENSIFIERS:
            intensify = 1.5
            steps.append({"word": word, "role": "intensifier", "effect": "1.5x next word"})
            continue

        if word in _POSITIVE_WORDS:
            if negate:
                neg_score += intensify
                steps.append({
                    "word": word, "role": "positive (negated)",
                    "effect": f"-{intensify}", "running_pos": pos_score, "running_neg": neg_score,
                })
            else:
                pos_score += intensify
                steps.append({
                    "word": word, "role": "positive",
                    "effect": f"+{intensify}", "running_pos": pos_score, "running_neg": neg_score,
                })
            negate = False
            intensify = 1.0
        elif word in _NEGATIVE_WORDS:
            if negate:
                pos_score += intensify
                steps.append({
                    "word": word, "role": "negative (negated)",
                    "effect": f"+{intensify}", "running_pos": pos_score, "running_neg": neg_score,
                })
            else:
                neg_score += intensify
                steps.append({
                    "word": word, "role": "negative",
                    "effect": f"-{intensify}", "running_pos": pos_score, "running_neg": neg_score,
                })
            negate = False
            intensify = 1.0
        else:
            negate = False
            intensify = 1.0

    total = pos_score + neg_score
    if total == 0:
        return {"score": None, "steps": steps, "pos": 0, "neg": 0,
                "summary": "No sentiment words detected."}
    raw = max(-1.0, min(1.0, (pos_score - neg_score) / total))
    return {
        "score": round(raw, 3),
        "pos": pos_score,
        "neg": neg_score,
        "steps": steps,
        "summary": f"Positive: {pos_score}, Negative: {neg_score}, Score: ({pos_score}-{neg_score})/{total} = {raw:.3f}",
    }


def get_validation_examples(conn: sqlite3.Connection, section: str,
                            limit: int = 3) -> list:
    """
    Pull real posts from the DB and run the detailed explainer for the
    requested section. Returns annotated examples.
    """
    # Pick posts that have relevant data and non-trivial text
    if section == "sentiment":
        rows = conn.execute("""
            SELECT id, title, selftext, sentiment FROM posts
            WHERE sentiment IS NOT NULL AND length(selftext) > 50
            ORDER BY ABS(sentiment) DESC LIMIT ?
        """, (limit,)).fetchall()
        examples = []
        for r in rows:
            text = f"{r['title']} {r['selftext']}"
            breakdown = explain_sentiment(text)
            examples.append({
                "post_id": r["id"],
                "title": r["title"],
                "text_preview": r["selftext"][:300],
                "stored_score": r["sentiment"],
                "breakdown": breakdown,
            })
        return examples

    elif section == "mentions":
        rows = conn.execute("""
            SELECT p.id, p.title, p.selftext FROM posts p
            JOIN mentions m ON m.post_id = p.id
            WHERE length(p.selftext) > 30
            GROUP BY p.id HAVING COUNT(m.contraceptive) >= 2
            ORDER BY p.score DESC LIMIT ?
        """, (limit,)).fetchall()
        examples = []
        for r in rows:
            text = f"{r['title']} {r['selftext']}"
            matches = explain_mentions(text)
            examples.append({
                "post_id": r["id"],
                "title": r["title"],
                "text_preview": r["selftext"][:300],
                "matches": matches,
            })
        return examples

    elif section in ("side_effects", "heatmap", "effects"):
        rows = conn.execute("""
            SELECT p.id, p.title, p.selftext FROM posts p
            JOIN side_effects se ON se.source_type = 'post' AND se.source_id = p.id
            WHERE length(p.selftext) > 30
            GROUP BY p.id HAVING COUNT(se.effect) >= 2
            ORDER BY p.score DESC LIMIT ?
        """, (limit,)).fetchall()
        examples = []
        for r in rows:
            text = f"{r['title']} {r['selftext']}"
            matches = explain_side_effects(text)
            mention_matches = explain_mentions(text)
            examples.append({
                "post_id": r["id"],
                "title": r["title"],
                "text_preview": r["selftext"][:300],
                "side_effect_matches": matches,
                "mention_matches": mention_matches,
            })
        return examples

    return []


USER_AGENT = "python:bc_tracker:v1.0 (educational contraceptive mention tracker)"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db(path: Optional[Path] = None) -> sqlite3.Connection:
    """Open (and initialize if needed) the SQLite database."""
    p = path or DB_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scrape_runs (
            id INTEGER PRIMARY KEY,
            scraped_at TEXT NOT NULL,
            post_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY,
            title TEXT,
            selftext TEXT,
            created_utc REAL,
            score INTEGER,
            num_comments INTEGER,
            permalink TEXT,
            first_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS mentions (
            post_id TEXT REFERENCES posts(id),
            contraceptive TEXT NOT NULL,
            PRIMARY KEY (post_id, contraceptive)
        );
        CREATE TABLE IF NOT EXISTS comments (
            id TEXT PRIMARY KEY,
            post_id TEXT REFERENCES posts(id),
            body TEXT,
            score INTEGER,
            created_utc REAL,
            author TEXT,
            sentiment REAL,
            first_seen TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS side_effects (
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            effect TEXT NOT NULL,
            PRIMARY KEY (source_type, source_id, effect)
        );
        CREATE TABLE IF NOT EXISTS scrape_errors (
            id INTEGER PRIMARY KEY,
            timestamp TEXT NOT NULL,
            subreddit TEXT,
            error_type TEXT NOT NULL,
            message TEXT,
            source_id TEXT,
            source_type TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mentions_type ON mentions(contraceptive);
        CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_utc);
        CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
        CREATE INDEX IF NOT EXISTS idx_side_effects_effect ON side_effects(effect);
        CREATE INDEX IF NOT EXISTS idx_errors_ts ON scrape_errors(timestamp);
    """)
    # Add columns if they don't exist yet (idempotent migration)
    for col, ctype in [
        ("sentiment", "REAL"),
        ("comments_scraped", "INTEGER DEFAULT 0"),
        ("subreddit", "TEXT DEFAULT 'birthcontrol'"),
        ("engagement_score", "REAL DEFAULT 0"),
        ("sort_source", "TEXT DEFAULT 'new'"),
        ("crosspost_parent", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE posts ADD COLUMN {col} {ctype}")
        except sqlite3.OperationalError:
            pass  # column already exists
    # scrape_runs columns
    for col, ctype in [
        ("subreddit", "TEXT DEFAULT 'birthcontrol'"),
        ("error_count", "INTEGER DEFAULT 0"),
    ]:
        try:
            conn.execute(f"ALTER TABLE scrape_runs ADD COLUMN {col} {ctype}")
        except sqlite3.OperationalError:
            pass
    # Index on subreddit (must be after ALTER TABLE adds the column)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit)")
    conn.row_factory = sqlite3.Row
    return conn


def compute_engagement(score: int, num_comments: int) -> float:
    """Engagement score: weights discussion (comments) higher than upvotes."""
    return math.log2(max(score, 1)) + math.log2(max(num_comments, 1)) * 1.5


def save_posts_to_db(conn: sqlite3.Connection, posts: list,
                     mention_map: dict, subreddit: str = "birthcontrol") -> int:
    """
    Upsert posts and their mentions into the database.
    Also computes sentiment, engagement, and side effects for each post.
    Skips mention/effect insertion for cross-posts (parent already counted).
    Returns number of new posts inserted.
    """
    now = datetime.utcnow().isoformat()
    new_count = 0
    for post in posts:
        text = f"{post['title']} {post['selftext']}"
        sent = score_sentiment(text)
        effects = find_side_effects(text)
        eng = compute_engagement(post["score"], post["num_comments"])
        xpost = post.get("crosspost_parent")
        sort_src = post.get("sort_source", "new")
        sub = post.get("subreddit", subreddit)

        cur = conn.execute(
            """INSERT INTO posts (id, title, selftext, created_utc, score,
                                  num_comments, permalink, first_seen, sentiment,
                                  subreddit, engagement_score, sort_source, crosspost_parent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   score = excluded.score,
                   num_comments = excluded.num_comments,
                   sentiment = excluded.sentiment,
                   engagement_score = MAX(posts.engagement_score, excluded.engagement_score),
                   sort_source = CASE WHEN excluded.sort_source = 'hot' THEN 'hot'
                                      ELSE posts.sort_source END""",
            (post["id"], post["title"], post["selftext"],
             post["created_utc"], post["score"], post["num_comments"],
             post["permalink"], now, sent,
             sub, eng, sort_src, xpost),
        )
        if cur.lastrowid:
            new_count += 1

        # Skip mention/effect analysis for cross-posts (parent post counts)
        if xpost:
            continue

        for ctype in mention_map.get(post["id"], []):
            conn.execute(
                "INSERT OR IGNORE INTO mentions (post_id, contraceptive) VALUES (?, ?)",
                (post["id"], ctype),
            )

        for effect in effects:
            conn.execute(
                "INSERT OR IGNORE INTO side_effects (source_type, source_id, effect) VALUES ('post', ?, ?)",
                (post["id"], effect),
            )

    conn.execute(
        "INSERT INTO scrape_runs (scraped_at, post_count, subreddit) VALUES (?, ?, ?)",
        (now, len(posts), subreddit),
    )
    conn.commit()
    return new_count


def save_comments_to_db(conn: sqlite3.Connection, post_id: str,
                        comments: list) -> int:
    """Save scraped comments, their mentions, sentiment, and side effects."""
    now = datetime.utcnow().isoformat()
    new_count = 0
    for c in comments:
        body = c.get("body", "")
        sent = score_sentiment(body)
        mentions = find_mentions(body)
        effects = find_side_effects(body)

        cur = conn.execute(
            """INSERT INTO comments (id, post_id, body, score, created_utc, author, sentiment, first_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET score = excluded.score, sentiment = excluded.sentiment""",
            (c["id"], post_id, body, c.get("score", 0),
             c.get("created_utc", 0), c.get("author", ""), sent, now),
        )
        if cur.lastrowid:
            new_count += 1

        for ctype in mentions:
            conn.execute(
                "INSERT OR IGNORE INTO mentions (post_id, contraceptive) VALUES (?, ?)",
                (post_id, ctype),
            )
        for effect in effects:
            conn.execute(
                "INSERT OR IGNORE INTO side_effects (source_type, source_id, effect) VALUES ('comment', ?, ?)",
                (c["id"], effect),
            )

    conn.execute(
        "UPDATE posts SET comments_scraped = 1 WHERE id = ?", (post_id,))
    conn.commit()
    return new_count


def migrate_legacy_json(conn: sqlite3.Connection) -> None:
    """One-time migration of old daily_mentions.json into the database."""
    if not LEGACY_JSON.exists():
        return
    row = conn.execute("SELECT COUNT(*) FROM scrape_runs").fetchone()
    if row[0] > 0:
        return

    print("Migrating legacy JSON data into SQLite...")
    data = json.loads(LEGACY_JSON.read_text())
    for date_str, day in data.get("days", {}).items():
        ts = f"{date_str}T00:00:00"
        conn.execute(
            "INSERT INTO scrape_runs (scraped_at, post_count) VALUES (?, ?)",
            (ts, day.get("total_posts", 0)),
        )
        for ctype, posts in day.get("top_posts", {}).items():
            for p in posts:
                conn.execute(
                    """INSERT OR IGNORE INTO posts
                       (id, title, selftext, created_utc, score,
                        num_comments, permalink, first_seen)
                       VALUES (?, ?, '', 0, ?, ?, ?, ?)""",
                    (p["id"], p["title"], p.get("score", 0),
                     p.get("num_comments", 0), p.get("permalink", ""), ts),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO mentions (post_id, contraceptive) VALUES (?, ?)",
                    (p["id"], ctype),
                )
    conn.commit()
    print("  Migration complete.")


def backfill_sentiment_and_effects(conn: sqlite3.Connection) -> None:
    """Backfill posts missing sentiment, engagement, or newly-matched mentions."""
    # Sentiment backfill
    rows = conn.execute(
        "SELECT id, title, selftext FROM posts WHERE sentiment IS NULL AND selftext != ''"
    ).fetchall()
    if rows:
        log.info(f"Backfilling sentiment & side effects for {len(rows)} existing posts...")
        for r in rows:
            text = f"{r['title']} {r['selftext']}"
            sent = score_sentiment(text)
            conn.execute("UPDATE posts SET sentiment = ? WHERE id = ?", (sent, r["id"]))
            for effect in find_side_effects(text):
                conn.execute(
                    "INSERT OR IGNORE INTO side_effects (source_type, source_id, effect) VALUES ('post', ?, ?)",
                    (r["id"], effect),
                )
        conn.commit()
        log.info("  Sentiment backfill complete.")

    # Engagement score backfill
    rows = conn.execute(
        "SELECT id, score, num_comments FROM posts WHERE engagement_score = 0 OR engagement_score IS NULL"
    ).fetchall()
    if rows:
        log.info(f"Backfilling engagement scores for {len(rows)} posts...")
        for r in rows:
            eng = compute_engagement(r["score"] or 0, r["num_comments"] or 0)
            conn.execute("UPDATE posts SET engagement_score = ? WHERE id = ?", (eng, r["id"]))
        conn.commit()

    # Re-run mention detection for expanded keywords (INSERT OR IGNORE = safe)
    rows = conn.execute(
        "SELECT id, title, selftext FROM posts WHERE selftext != '' AND crosspost_parent IS NULL"
    ).fetchall()
    new_mentions = 0
    for r in rows:
        text = f"{r['title']} {r['selftext']}"
        for ctype in find_mentions(text):
            cur = conn.execute(
                "INSERT OR IGNORE INTO mentions (post_id, contraceptive) VALUES (?, ?)",
                (r["id"], ctype),
            )
            if cur.rowcount:
                new_mentions += 1
    if new_mentions:
        conn.commit()
        log.info(f"  Found {new_mentions} new mentions from expanded keywords.")


# ---------------------------------------------------------------------------
# Error logging helpers
# ---------------------------------------------------------------------------

def save_error_to_db(conn: sqlite3.Connection, subreddit: str, error_type: str,
                     message: str, source_id: Optional[str] = None,
                     source_type: Optional[str] = None) -> None:
    conn.execute(
        """INSERT INTO scrape_errors (timestamp, subreddit, error_type, message, source_id, source_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (datetime.utcnow().isoformat(), subreddit, error_type, message, source_id, source_type),
    )
    conn.commit()


def query_recent_errors(conn: sqlite3.Connection, limit: int = 50) -> list:
    rows = conn.execute(
        "SELECT * FROM scrape_errors ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def query_error_count(conn: sqlite3.Connection, hours: int = 24) -> int:
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    return conn.execute(
        "SELECT COUNT(*) FROM scrape_errors WHERE timestamp >= ?", (cutoff,)
    ).fetchone()[0]


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------

def _add_date_filter(sql: str, params: list, date_from: Optional[float],
                     date_to: Optional[float], col: str = "p.created_utc") -> str:
    """Append date range WHERE clauses. Returns updated sql."""
    if date_from is not None:
        sql += f" AND {col} >= ?"
        params.append(date_from)
    if date_to is not None:
        sql += f" AND {col} <= ?"
        params.append(date_to)
    return sql


def query_mention_counts(conn: sqlite3.Connection,
                         date_from: Optional[float] = None,
                         date_to: Optional[float] = None,
                         subreddit: Optional[str] = None) -> list:
    sql = "SELECT m.contraceptive, COUNT(*) as cnt FROM mentions m"
    wheres = []
    params = []
    need_join = date_from is not None or date_to is not None or subreddit is not None
    if need_join:
        sql += " JOIN posts p ON p.id = m.post_id"
    if date_from is not None:
        wheres.append("p.created_utc >= ?")
        params.append(date_from)
    if date_to is not None:
        wheres.append("p.created_utc <= ?")
        params.append(date_to)
    if subreddit is not None:
        wheres.append("p.subreddit = ?")
        params.append(subreddit)
    if wheres:
        sql += " WHERE " + " AND ".join(wheres)
    sql += " GROUP BY m.contraceptive ORDER BY cnt DESC"
    return [(r[0], r[1]) for r in conn.execute(sql, params).fetchall()]


def query_daily_counts(conn: sqlite3.Connection,
                       date_from: Optional[float] = None,
                       date_to: Optional[float] = None,
                       subreddit: Optional[str] = None) -> dict:
    sql = """
        SELECT date(p.created_utc, 'unixepoch') as day,
               m.contraceptive, COUNT(*) as cnt
        FROM mentions m JOIN posts p ON p.id = m.post_id
        WHERE p.created_utc > 0
    """
    params = []
    if date_from is not None:
        sql += " AND p.created_utc >= ?"
        params.append(date_from)
    if date_to is not None:
        sql += " AND p.created_utc <= ?"
        params.append(date_to)
    if subreddit is not None:
        sql += " AND p.subreddit = ?"
        params.append(subreddit)
    sql += " GROUP BY day, m.contraceptive ORDER BY day"
    result = {}
    for row in conn.execute(sql, params).fetchall():
        result.setdefault(row[0], {})[row[1]] = row[2]
    return result


def query_top_posts(conn: sqlite3.Connection, contraceptive: str,
                    limit: int = 20, subreddit: Optional[str] = None,
                    date_from: Optional[float] = None,
                    date_to: Optional[float] = None) -> list:
    sql = """
        SELECT p.id, p.title, p.selftext, p.created_utc, p.score,
               p.num_comments, p.permalink, p.sentiment, p.subreddit,
               p.engagement_score
        FROM posts p JOIN mentions m ON m.post_id = p.id
        WHERE m.contraceptive = ?
    """
    params = [contraceptive]
    if date_from is not None:
        sql += " AND p.created_utc >= ?"
        params.append(date_from)
    if date_to is not None:
        sql += " AND p.created_utc <= ?"
        params.append(date_to)
    if subreddit is not None:
        sql += " AND p.subreddit = ?"
        params.append(subreddit)
    sql += " ORDER BY p.engagement_score DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def query_db_stats(conn: sqlite3.Connection) -> dict:
    total_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    total_mentions = conn.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
    total_scrapes = conn.execute("SELECT COUNT(*) FROM scrape_runs").fetchone()[0]
    total_comments = conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    last_scrape = conn.execute(
        "SELECT scraped_at FROM scrape_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    avg_sent = conn.execute(
        "SELECT AVG(sentiment) FROM posts WHERE sentiment IS NOT NULL"
    ).fetchone()[0]
    subreddit_count = conn.execute(
        "SELECT COUNT(DISTINCT subreddit) FROM posts WHERE subreddit IS NOT NULL"
    ).fetchone()[0]
    error_count_24h = query_error_count(conn, hours=24)
    return {
        "total_posts": total_posts,
        "total_mentions": total_mentions,
        "total_scrapes": total_scrapes,
        "total_comments": total_comments,
        "last_scrape": last_scrape[0] if last_scrape else None,
        "avg_sentiment": round(avg_sent, 3) if avg_sent is not None else None,
        "subreddit_count": subreddit_count or 0,
        "error_count_24h": error_count_24h,
    }


def query_sentiment_by_type(conn: sqlite3.Connection,
                            date_from: Optional[float] = None,
                            date_to: Optional[float] = None,
                            subreddit: Optional[str] = None) -> list:
    """Return [(contraceptive, avg_sentiment, post_count)] sorted by avg sentiment."""
    sql = """
        SELECT m.contraceptive, AVG(p.sentiment) as avg_s, COUNT(*) as cnt
        FROM mentions m JOIN posts p ON p.id = m.post_id
        WHERE p.sentiment IS NOT NULL
    """
    params = []
    if date_from is not None:
        sql += " AND p.created_utc >= ?"
        params.append(date_from)
    if date_to is not None:
        sql += " AND p.created_utc <= ?"
        params.append(date_to)
    if subreddit is not None:
        sql += " AND p.subreddit = ?"
        params.append(subreddit)
    sql += " GROUP BY m.contraceptive HAVING cnt >= 2 ORDER BY avg_s DESC"
    return [(r[0], round(r[1], 3), r[2]) for r in conn.execute(sql, params).fetchall()]


def query_side_effect_counts(conn: sqlite3.Connection,
                             date_from: Optional[float] = None,
                             date_to: Optional[float] = None,
                             contraceptive: Optional[str] = None,
                             subreddit: Optional[str] = None) -> list:
    """Return [(effect, count)] sorted by count desc."""
    sql = "SELECT se.effect, COUNT(DISTINCT se.source_id) as cnt FROM side_effects se"
    wheres = []
    params = []
    need_filter = date_from is not None or date_to is not None or contraceptive is not None or subreddit is not None

    if need_filter:
        sql += """
            LEFT JOIN posts p ON (se.source_type = 'post' AND se.source_id = p.id)
            LEFT JOIN comments c ON (se.source_type = 'comment' AND se.source_id = c.id)
        """
        if date_from is not None:
            wheres.append("(COALESCE(p.created_utc, c.created_utc) >= ?)")
            params.append(date_from)
        if date_to is not None:
            wheres.append("(COALESCE(p.created_utc, c.created_utc) <= ?)")
            params.append(date_to)
        if contraceptive is not None:
            sql += " JOIN mentions m ON m.post_id = COALESCE(p.id, c.post_id)"
            wheres.append("m.contraceptive = ?")
            params.append(contraceptive)
        if subreddit is not None:
            wheres.append("COALESCE(p.subreddit, (SELECT p2.subreddit FROM posts p2 WHERE p2.id = c.post_id)) = ?")
            params.append(subreddit)

    if wheres:
        sql += " WHERE " + " AND ".join(wheres)
    sql += " GROUP BY se.effect ORDER BY cnt DESC"
    return [(r[0], r[1]) for r in conn.execute(sql, params).fetchall()]


def query_side_effects_by_contraceptive(conn: sqlite3.Connection,
                                        date_from: Optional[float] = None,
                                        date_to: Optional[float] = None,
                                        subreddit: Optional[str] = None) -> dict:
    """Return {contraceptive: {effect: count}} for the heatmap."""
    sql = """
        SELECT m.contraceptive, se.effect, COUNT(DISTINCT se.source_id) as cnt
        FROM side_effects se
        JOIN posts p ON (se.source_type = 'post' AND se.source_id = p.id)
        JOIN mentions m ON m.post_id = p.id
        WHERE p.created_utc > 0
    """
    params = []
    if date_from is not None:
        sql += " AND p.created_utc >= ?"
        params.append(date_from)
    if date_to is not None:
        sql += " AND p.created_utc <= ?"
        params.append(date_to)
    if subreddit is not None:
        sql += " AND p.subreddit = ?"
        params.append(subreddit)
    sql += " GROUP BY m.contraceptive, se.effect"

    sql2 = """
        UNION ALL
        SELECT m.contraceptive, se.effect, COUNT(DISTINCT se.source_id) as cnt
        FROM side_effects se
        JOIN comments c ON (se.source_type = 'comment' AND se.source_id = c.id)
        JOIN mentions m ON m.post_id = c.post_id
        WHERE c.created_utc > 0
    """
    if date_from is not None:
        sql2 += " AND c.created_utc >= ?"
        params.append(date_from)
    if date_to is not None:
        sql2 += " AND c.created_utc <= ?"
        params.append(date_to)
    if subreddit is not None:
        sql2 += " AND (SELECT p3.subreddit FROM posts p3 WHERE p3.id = c.post_id) = ?"
        params.append(subreddit)
    sql2 += " GROUP BY m.contraceptive, se.effect"

    full = f"SELECT contraceptive, effect, SUM(cnt) as total FROM ({sql} {sql2}) GROUP BY contraceptive, effect"
    result = {}
    for row in conn.execute(full, params).fetchall():
        result.setdefault(row[0], {})[row[1]] = row[2]
    return result


def query_comments_for_post(conn: sqlite3.Connection, post_id: str) -> list:
    rows = conn.execute("""
        SELECT id, body, score, created_utc, author, sentiment
        FROM comments WHERE post_id = ? ORDER BY score DESC
    """, (post_id,)).fetchall()
    return [dict(r) for r in rows]


def export_all_data(conn: sqlite3.Connection) -> dict:
    """Export all raw data as dicts for static site generation."""
    posts = [dict(r) for r in conn.execute("""
        SELECT id, created_utc, subreddit, score, num_comments, sentiment,
               engagement_score, title, substr(selftext, 1, 300) as selftext, permalink
        FROM posts WHERE created_utc > 0
        ORDER BY created_utc DESC
    """).fetchall()]

    mentions = [(r[0], r[1]) for r in conn.execute(
        "SELECT post_id, contraceptive FROM mentions"
    ).fetchall()]

    side_effects = [(r[0], r[1], r[2]) for r in conn.execute(
        "SELECT source_type, source_id, effect FROM side_effects"
    ).fetchall()]

    comments = [dict(r) for r in conn.execute("""
        SELECT id, post_id, substr(body, 1, 200) as body, score, author, sentiment
        FROM comments ORDER BY score DESC
    """).fetchall()]

    stats = query_db_stats(conn)

    return {
        "posts": posts,
        "mentions": mentions,
        "side_effects": side_effects,
        "comments": comments,
        "stats": stats,
    }


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def backup_db() -> Optional[str]:
    dropbox_root = BACKUP_DIR.parent.parent
    if not dropbox_root.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    dest = BACKUP_DIR / f"tracker-{today}.db"
    src_conn = sqlite3.connect(str(DB_FILE))
    dst_conn = sqlite3.connect(str(dest))
    src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()
    project_dir = Path(__file__).parent
    for fname in ["bc_tracker.py", "bc_tracker_web.py", "CLAUDE.md"]:
        src = project_dir / fname
        if src.exists():
            shutil.copy2(str(src), str(BACKUP_DIR / fname))
    backups = sorted(BACKUP_DIR.glob("tracker-*.db"), reverse=True)
    for old in backups[7:]:
        old.unlink()
    return str(dest)


# ---------------------------------------------------------------------------
# Reddit scraping
# ---------------------------------------------------------------------------

def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def scrape_subreddit(subreddit: str = "birthcontrol", limit: int = 200,
                     sort: str = "new") -> list:
    posts = []
    base = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
    after = None
    seen_ids = set()
    while len(posts) < limit:
        url = f"{base}?limit=100&raw_json=1"
        if after:
            url += f"&after={after}"
        try:
            data = fetch_json(url)
        except urllib.error.HTTPError as e:
            log.error(f"HTTP {e.code} scraping r/{subreddit}/{sort}: {e.reason}")
            break
        except urllib.error.URLError as e:
            log.error(f"Network error scraping r/{subreddit}/{sort}: {e.reason}")
            break
        children = data.get("data", {}).get("children", [])
        if not children:
            break
        for child in children:
            d = child["data"]
            if d["id"] in seen_ids:
                continue
            seen_ids.add(d["id"])
            xpost_list = d.get("crosspost_parent_list", [])
            xpost_parent = xpost_list[0].get("id") if xpost_list else None
            posts.append({
                "id": d["id"], "title": d.get("title", ""),
                "selftext": d.get("selftext", ""),
                "created_utc": d.get("created_utc", 0),
                "score": d.get("score", 0),
                "num_comments": d.get("num_comments", 0),
                "permalink": d.get("permalink", ""),
                "subreddit": subreddit,
                "sort_source": sort,
                "crosspost_parent": xpost_parent,
            })
        after = data["data"].get("after")
        if not after:
            break
        time.sleep(1.5)
    return posts


def scrape_comments_for_post(post_id: str, permalink: str) -> list:
    """Fetch all comments for a single post, walking the reply tree."""
    url = f"https://www.reddit.com{permalink}.json?raw_json=1&limit=200"
    try:
        data = fetch_json(url)
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        log.error(f"Comment fetch failed for {post_id}: {e}")
        return []

    comments = []
    if len(data) < 2:
        return comments

    def walk_tree(node):
        if isinstance(node, dict):
            kind = node.get("kind")
            if kind == "t1":
                d = node.get("data", {})
                if d.get("body") and d.get("body") != "[deleted]":
                    comments.append({
                        "id": d["id"],
                        "body": d.get("body", ""),
                        "score": d.get("score", 0),
                        "created_utc": d.get("created_utc", 0),
                        "author": d.get("author", ""),
                    })
                replies = d.get("replies")
                if isinstance(replies, dict):
                    walk_tree(replies)
            elif kind == "Listing":
                for child in node.get("data", {}).get("children", []):
                    walk_tree(child)

    walk_tree(data[1])
    return comments


def scrape_comments_batch(conn: sqlite3.Connection, limit: int = 50) -> int:
    """Scrape comments for posts that haven't been scraped yet. Returns total new comments."""
    rows = conn.execute("""
        SELECT DISTINCT p.id, p.permalink
        FROM posts p JOIN mentions m ON m.post_id = p.id
        WHERE p.comments_scraped = 0 AND p.permalink != ''
        ORDER BY p.created_utc DESC LIMIT ?
    """, (limit,)).fetchall()

    if not rows:
        return 0

    total_new = 0
    print(f"Scraping comments for {len(rows)} posts...")
    for i, row in enumerate(rows):
        comments = scrape_comments_for_post(row["id"], row["permalink"])
        if comments:
            n = save_comments_to_db(conn, row["id"], comments)
            total_new += n
            print(f"  [{i+1}/{len(rows)}] {row['id']}: {len(comments)} comments ({n} new)")
        else:
            # Mark as scraped even if no comments found
            conn.execute("UPDATE posts SET comments_scraped = 1 WHERE id = ?", (row["id"],))
            conn.commit()
        time.sleep(1.5)

    return total_new


def analyze_posts(posts: list) -> dict:
    """Return {post_id: [contraceptive_names]} for all posts."""
    result = {}
    for post in posts:
        combined = f"{post['title']} {post['selftext']}"
        mentions = find_mentions(combined)
        if mentions:
            result[post["id"]] = mentions
    return result


# ---------------------------------------------------------------------------
# Public scrape function (used by both CLI and web server)
# ---------------------------------------------------------------------------

def run_scrape(limit: int = 200, filter_today: bool = False) -> dict:
    now = datetime.utcnow()
    log.info(f"Starting multi-subreddit scrape ({now.strftime('%Y-%m-%d %H:%M UTC')})...")

    conn = get_db()
    migrate_legacy_json(conn)
    backfill_sentiment_and_effects(conn)

    total_fetched = 0
    total_new = 0
    all_mention_counts = Counter()
    error_count = 0

    for sub_config in SUBREDDITS:
        sub_name = sub_config["name"]
        sub_limit = sub_config["limit"]
        log.info(f"  Scraping r/{sub_name} ({sub_limit} /new + 50 /hot)...")

        try:
            posts_new = scrape_subreddit(subreddit=sub_name, limit=sub_limit, sort="new")
            posts_hot = scrape_subreddit(subreddit=sub_name, limit=min(sub_limit, 50), sort="hot")
            posts = posts_new + posts_hot
        except Exception as e:
            log.error(f"Failed to scrape r/{sub_name}: {e}")
            save_error_to_db(conn, sub_name, "scrape_failure", str(e))
            error_count += 1
            continue

        if not posts:
            log.info(f"    No posts from r/{sub_name}")
            continue

        if filter_today:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day_ts = day_start.timestamp()
            posts = [p for p in posts if p["created_utc"] >= day_ts]

        mention_map = analyze_posts(posts)
        new_count = save_posts_to_db(conn, posts, mention_map, subreddit=sub_name)
        total_fetched += len(posts)
        total_new += new_count

        for ctypes in mention_map.values():
            for c in ctypes:
                all_mention_counts[c] += 1

        log.info(f"    r/{sub_name}: {len(posts)} fetched, {new_count} new, {len(mention_map)} with mentions")

    # Scrape comments for posts with mentions (across all subs)
    new_comments = scrape_comments_batch(conn, limit=50)
    log.info(f"  {new_comments} new comments saved.")

    log.info(f"\nMentions found across all subreddits:")
    for name, count in all_mention_counts.most_common():
        log.info(f"  {name:25s} {count}")

    stats = query_db_stats(conn)
    conn.close()

    log.info(f"Totals: {stats['total_posts']} posts, {stats['total_comments']} comments, {error_count} errors")

    bk = backup_db()
    if bk:
        log.info(f"Backup saved to {bk}")

    return {
        "ok": True,
        "posts_fetched": total_fetched,
        "new_posts": total_new,
        "new_comments": new_comments,
        "mention_counts": dict(all_mention_counts),
        "db_total_posts": stats["total_posts"],
        "db_total_comments": stats["total_comments"],
        "error_count": error_count,
    }


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_scrape(args: argparse.Namespace) -> None:
    run_scrape(limit=args.limit, filter_today=not args.all)


def cmd_report(args: argparse.Namespace) -> None:
    conn = get_db()
    migrate_legacy_json(conn)
    backfill_sentiment_and_effects(conn)

    stats = query_db_stats(conn)
    if stats["total_posts"] == 0:
        print("No data yet. Run `python bc_tracker.py scrape` first.")
        conn.close()
        return

    df = (datetime.utcnow() - timedelta(days=args.days)).timestamp() if args.days else None
    counts = query_mention_counts(conn, date_from=df)
    daily = query_daily_counts(conn, date_from=df)
    sentiment = query_sentiment_by_type(conn, date_from=df)
    effects = query_side_effect_counts(conn, date_from=df)
    conn.close()

    dates = sorted(daily.keys())
    total_mentions = sum(c for _, c in counts)

    print("=" * 70)
    print("  Contraceptive Reddit Tracker — Multi-Subreddit Report")
    print("=" * 70)
    if dates:
        print(f"  Period      : {dates[0]} to {dates[-1]} ({len(dates)} day(s))")
    print(f"  DB posts    : {stats['total_posts']}")
    print(f"  DB comments : {stats['total_comments']}")
    print(f"  Scrape runs : {stats['total_scrapes']}")
    print(f"  Avg sentiment: {stats['avg_sentiment']}")
    print("-" * 70)

    # Mention counts
    if counts:
        max_count = counts[0][1]
        print(f"\n  {'Contraceptive':<25s} {'Count':>5s}  Distribution")
        print(f"  {'-'*25} {'-'*5}  {'-'*30}")
        for name, count in counts:
            bar_len = int((count / max_count) * 30)
            print(f"  {name:<25s} {count:>5d}  {'#' * bar_len}")

    # Sentiment
    if sentiment:
        print(f"\n  {'Contraceptive':<25s} {'Sentiment':>9s}  {'Posts':>5s}")
        print(f"  {'-'*25} {'-'*9}  {'-'*5}")
        for name, avg_s, cnt in sentiment:
            indicator = "+" if avg_s > 0 else ""
            print(f"  {name:<25s} {indicator}{avg_s:>8.3f}  {cnt:>5d}")

    # Side effects
    if effects:
        print(f"\n  Top Side Effects / Worries:")
        print(f"  {'-'*40}")
        for effect, cnt in effects[:15]:
            print(f"  {effect:<30s} {cnt:>5d} mentions")

    # Daily breakdown
    if dates:
        print(f"\n  Daily breakdown (top 5 per day):")
        print(f"  {'-'*50}")
        for date in dates[-10:]:
            day_counts = daily[date]
            top5 = sorted(day_counts.items(), key=lambda x: -x[1])[:5]
            summary = ", ".join(f"{n}({c})" for n, c in top5)
            print(f"  {date}: {summary}")

    print("=" * 70)

    if args.csv:
        csv_path = DATA_DIR / "report.csv"
        with open(csv_path, "w") as f:
            f.write("date,contraceptive,mentions\n")
            for date in dates:
                for name, count in daily[date].items():
                    f.write(f"{date},{name},{count}\n")
        print(f"  CSV exported to {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Track contraceptive mentions across multiple subreddits"
    )
    sub = parser.add_subparsers(dest="command")

    sp_scrape = sub.add_parser("scrape", help="Scrape subreddit and save data")
    sp_scrape.add_argument("--limit", type=int, default=200)
    sp_scrape.add_argument("--all", action="store_true",
                           help="Include all fetched posts, not just today's")
    sp_scrape.set_defaults(func=cmd_scrape)

    sp_report = sub.add_parser("report", help="Generate summary report")
    sp_report.add_argument("--days", type=int, default=None)
    sp_report.add_argument("--csv", action="store_true")
    sp_report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
