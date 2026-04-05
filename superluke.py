"""
Luke Superluke
================
A chat-based second brain that watches your screen and remembers everything.

Architecture:
  - ScreenReaderAgent   → every 10s, captures + reads screen via Groq vision (only on diff)
  - SummaryAgent        → every 2min, clock-aligned (e.g. 2:00, 2:02, 2:04...)
                          drains the in-memory raw buffer, asks Groq to synthesize
                          a window summary, writes to summaries.json
  - MemoryAgent         → pure JSON storage + keyword retrieval, no ChromaDB
  - ChatAgent           → routes queries, builds context, answers

Storage (all in ~/.luke/):
  - raw_buffer          → in-memory only (list), never written to disk mid-window
                          to avoid partial reads. Drained atomically at each window.
  - summaries.json      → list of 2-min window summaries (permanent log)
  - entities.json       → structured data: jobs, deadlines, links, research, people, projects
  - orphan_buffer.json  → written on clean shutdown so next startup can recover
                          any unprocessed snapshots

Threading model:
  - _buffer_lock        → protects raw_buffer (screenshot thread writes, summary thread drains)
  - _file_lock          → protects all JSON file writes (summary + entity upserts)
  Both locks are never held simultaneously to prevent deadlock.

Run:
    python superluke.py watch    # background screen watcher only
    python superluke.py chat     # chat with memory only
    python superluke.py          # both together (recommended)
"""

import time
import json
import re
import os
import base64
import threading
import signal
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path

import mss
from PIL import Image
from groq import Groq

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional; set GROQ_API_KEY in environment or .env manually

# ══════════════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════════════

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file or environment.")
groq_client       = Groq(api_key=GROQ_API_KEY)
VISION_MODEL      = "meta-llama/llama-4-scout-17b-16e-instruct"
FAST_MODEL        = "meta-llama/llama-4-scout-17b-16e-instruct"

CAPTURE_INTERVAL  = 10          # seconds between screenshot polls
DIFF_THRESHOLD    = 0.02        # pixel diff % to trigger vision call
SUMMARY_INTERVAL  = 2           # minutes per clock-aligned summary window

MEMORY_DIR        = Path.home() / ".luke"
MEMORY_DIR.mkdir(exist_ok=True)

SUMMARIES_FILE    = MEMORY_DIR / "summaries.json"
ENTITIES_FILE     = MEMORY_DIR / "entities.json"
TASKS_FILE        = MEMORY_DIR / "tasks.json"
ORPHAN_FILE       = MEMORY_DIR / "orphan_buffer.json"  # crash recovery

# ══════════════════════════════════════════════════════════════════════════════
# Shared state — raw snapshot buffer
# ══════════════════════════════════════════════════════════════════════════════

_raw_buffer: list  = []       # list of snapshot dicts from ScreenReaderAgent
_buffer_lock       = threading.Lock()
_file_lock         = threading.Lock()

# ══════════════════════════════════════════════════════════════════════════════
# Utilities
# ══════════════════════════════════════════════════════════════════════════════

def get_scale_factor() -> float:
    try:
        from AppKit import NSScreen
        return NSScreen.mainScreen().backingScaleFactor()
    except ImportError:
        try:
            import ctypes
            return ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
        except Exception:
            return 1.0

SCALE = get_scale_factor()


def take_screenshot() -> Image.Image:
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)
        return Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")


def images_are_different(img1: Image.Image, img2: Image.Image) -> bool:
    import numpy as np
    a = np.array(img1.resize((320, 180))).astype(float)
    b = np.array(img2.resize((320, 180))).astype(float)
    return (abs(a - b).mean() / 255.0) > DIFF_THRESHOLD


def pil_to_base64(img: Image.Image) -> str:
    img = img.copy()
    img.thumbnail((1280, 1280), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def groq_vision(img: Image.Image, prompt: str) -> str:
    r = groq_client.chat.completions.create(
        model=VISION_MODEL,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{pil_to_base64(img)}"}},
            {"type": "text", "text": prompt}
        ]}],
        max_tokens=1024, temperature=0.1
    )
    return r.choices[0].message.content.strip()


def groq_text(messages: list) -> str:
    r = groq_client.chat.completions.create(
        model=FAST_MODEL,
        messages=messages,
        max_tokens=1024, temperature=0.2
    )
    return r.choices[0].message.content.strip()


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return default
    return default


# ── Async write queue ──────────────────────────────────────────────────────────
# All JSON writes are dispatched here so screenshot/summary loops never block
# on disk I/O. A single background writer thread drains the queue in order,
# ensuring writes to the same file are always serialised (no torn writes).
# _file_lock is no longer needed for writes — the queue is the serialisation
# point. It is kept for read-modify-write sequences in _upsert_entities where
# the load + mutate + enqueue must be atomic.

_write_queue: "queue.Queue[tuple[Path, object]]" = None   # initialised in _start_writer

def _start_writer():
    import queue as _q
    global _write_queue
    _write_queue = _q.Queue()

    def _writer():
        while True:
            path, data = _write_queue.get()
            try:
                path.write_text(json.dumps(data, indent=2, default=str))
            except Exception as e:
                print(f"  [write error] {path.name}: {e}")
            finally:
                _write_queue.task_done()

    t = threading.Thread(target=_writer, daemon=True, name="json-writer")
    t.start()

def save_json_async(path: Path, data):
    """Enqueue a JSON write. Returns immediately; disk write happens in background."""
    _write_queue.put((path, data))


def uid(prefix: str) -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"


def current_window_start(now: datetime = None) -> datetime:
    """
    Returns the start of the current clock-aligned SUMMARY_INTERVAL window.
    E.g. if SUMMARY_INTERVAL=2 and now=14:07:43, returns 14:06:00.
    """
    if now is None:
        now = datetime.now()
    minute_block = (now.minute // SUMMARY_INTERVAL) * SUMMARY_INTERVAL
    return now.replace(minute=minute_block, second=0, microsecond=0)


def next_window_start(now: datetime = None) -> datetime:
    if now is None:
        now = datetime.now()
    return current_window_start(now) + timedelta(minutes=SUMMARY_INTERVAL)


def seconds_until_next_window(now: datetime = None) -> float:
    if now is None:
        now = datetime.now()
    return (next_window_start(now) - now).total_seconds()


# ══════════════════════════════════════════════════════════════════════════════
# Agent 1 — ScreenReaderAgent
# Reads a screenshot, returns structured JSON. Single responsibility.
# ══════════════════════════════════════════════════════════════════════════════

class ScreenReaderAgent:

    PROMPT = """Analyze this screenshot. Return ONLY valid JSON, no markdown, no explanation.

CATEGORIES (pick exactly one for screen_category):
  PRODUCTIVE:   coding | writing | learning | research | email | meeting | ai_tools | design | productivity_tools
  NEUTRAL:      job_search | communication | browsing
  UNPRODUCTIVE: youtube_video | social_media | gaming | distraction
  SYSTEM:       idle | other

CATEGORY RULES (read carefully):
- coding        → IDE, terminal, code editor, GitHub, any programming
- writing       → Docs, Notion, Word, notes, writing anything
- learning      → YouTube tutorials/courses/how-to, Coursera, documentation, Stack Overflow, educational content
- youtube_video → YouTube but NOT tutorials — home page, entertainment, music, vlogs
- research      → Google Scholar, arXiv, reading technical articles or papers
- email         → Gmail, Outlook, Apple Mail — reading or writing emails
- meeting       → Zoom, Meet, Teams, any video call
- ai_tools      → Claude, ChatGPT, Copilot, Perplexity, Gemini, any AI assistant
- design        → Figma, Sketch, Canva, Photoshop, Illustrator
- productivity_tools → Calendar, Todoist, task managers, Notion planning
- job_search    → LinkedIn (job searching OR scrolling), Jobbright, Workday, company career pages, job applications
- communication → Slack, Discord, iMessage — text-based work communication
- social_media  → Instagram, Twitter/X, Facebook, TikTok, LinkedIn feed scrolling
- gaming        → Steam, any game, game-related content
- distraction   → Reddit casual, news scrolling, shopping, anything clearly unproductive
- browsing      → general web browsing not fitting any other category
- idle          → lock screen, desktop, screensaver, no activity

KEY DISTINCTIONS:
- YouTube: check the page title. If title contains "tutorial", "course", "how to", "learn", "explained", "guide", "lecture" → learning. Otherwise → youtube_video
- LinkedIn: ALWAYS → job_search (whether applying or browsing feed)
- Reddit: technical subreddits (r/programming, r/MachineLearning, etc.) → research. Casual browsing → distraction
- Browser apps: categorize by URL/content, NOT the browser name

{
  "app": "app currently in focus",
  "screen_title": "concise label e.g. 'YouTube · Tutorial: React Hooks' or 'LinkedIn · Job Search' or 'VS Code · superluke.py'",
  "screen_category": "one category from the list above",
  "productive": true or false (coding/writing/learning/research/email/meeting/ai_tools/design/productivity_tools = true, everything else = false),
  "summary": "1-2 sentences: exactly what is the user doing right now",
  "url": "full URL if browser is visible, else null",
  "file": "filename if code editor or doc editor visible, else null",
  "activity": "coding|writing|browsing|email|video|meeting|reading|design|idle|job_search|other",

  "entities": {
    "deadlines": [
      { "title": "task or deadline name", "due_date": "YYYY-MM-DD or null", "notes": "any extra context" }
    ],
    "job_applications": [
      { "company": "Company Name", "role": "Job Title", "status": "saved|applied|interviewing|offered|rejected" }
    ],
    "links": [
      { "url": "full url", "title": "page title", "topic": "what this page is about in 3-5 words" }
    ],
    "research_topics": [
      { "topic": "topic name", "summary": "one line of what was being researched" }
    ],
    "people": [
      { "name": "Full Name", "context": "who they are or why relevant" }
    ],
    "projects": ["project name if clearly visible"],
    "tasks": [
      { "title": "exact task or action item addressed TO the user", "due_date": "YYYY-MM-DD or null", "priority": "high|normal|low", "context": "where this was seen e.g. email, doc, slack" }
    ]
  }
}

Rules for tasks: ONLY include tasks clearly directed at or owned by the user (not someone else's to-do list).
JSON only. No markdown fences."""

    def read(self, img: Image.Image, timestamp: datetime) -> dict:
        raw = groq_vision(img, self.PROMPT)
        raw = re.sub(r"```json|```", "", raw).strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {
                "app": "unknown", "screen_title": "Unknown", "screen_category": "other",
                "productive": False, "summary": raw[:200], "url": None,
                "file": None, "activity": "other",
                "entities": {
                    "deadlines": [], "job_applications": [],
                    "links": [], "research_topics": [], "people": [], "projects": [], "tasks": []
                }
            }
        parsed["_ts"]   = timestamp.isoformat()
        parsed["_time"] = timestamp.strftime("%H:%M:%S")
        parsed["_date"] = timestamp.strftime("%Y-%m-%d")
        return parsed


# ══════════════════════════════════════════════════════════════════════════════
# Agent 2 — SummaryAgent
# Drains the raw buffer every 2min, synthesizes a window summary.
# Runs on its own thread, clock-aligned.
# ══════════════════════════════════════════════════════════════════════════════

class SummaryAgent:

    SUMMARY_PROMPT = """You are summarizing a user's screen activity during a {duration}-minute window ({window_start} to {window_end}).

Here are the raw screen snapshots captured during that window:
{snapshots}

Return ONLY valid JSON:
{{
  "narrative": "2-4 sentence human-readable summary of what the user did this window",
  "primary_activity": "the dominant activity type",
  "apps_used": ["list", "of", "apps"],
  "urls_visited": ["list of urls seen, deduplicated"],
  "files_open": ["list of filenames seen, deduplicated"],
  "key_topics": ["3-5 keyword topics that describe this window"]
}}

JSON only. No markdown fences."""

    def __init__(self, memory_agent):
        self.memory = memory_agent

    def synthesize_window(self, snapshots: list, window_start: datetime, window_end: datetime) -> dict:
        """Call Groq to compress N snapshots into one window summary."""
        if not snapshots:
            return None

        # Build a compact text representation of the snapshots
        snap_text = ""
        for i, s in enumerate(snapshots, 1):
            snap_text += f"\n[{s.get('_time','?')}] app={s.get('app','?')} category={s.get('screen_category','?')} productive={s.get('productive','?')}\n"
            snap_text += f"  title: {s.get('screen_title','')}\n"
            snap_text += f"  summary: {s.get('summary','')}\n"
            if s.get("url"):
                snap_text += f"  url: {s['url']}\n"
            if s.get("file"):
                snap_text += f"  file: {s['file']}\n"

        prompt = self.SUMMARY_PROMPT.format(
            duration=SUMMARY_INTERVAL,
            window_start=window_start.strftime("%H:%M"),
            window_end=window_end.strftime("%H:%M"),
            snapshots=snap_text
        )

        raw = groq_text([{"role": "user", "content": prompt}])
        raw = re.sub(r"```json|```", "", raw).strip()

        try:
            synthesis = json.loads(raw)
        except json.JSONDecodeError:
            synthesis = {
                "narrative": raw[:300],
                "primary_activity": "unknown",
                "apps_used": [],
                "urls_visited": [],
                "files_open": [],
                "key_topics": []
            }

        # Collect all entities seen across snapshots in this window
        merged_entities = defaultdict(list)
        for s in snapshots:
            for key, val in s.get("entities", {}).items():
                if isinstance(val, list):
                    merged_entities[key].extend(val)

        # Aggregate category time (seconds per category in this window)
        category_counts: dict = defaultdict(int)
        productive_count = 0
        for s in snapshots:
            cat = s.get("screen_category", "other")
            category_counts[cat] += 1
            if s.get("productive", False):
                productive_count += 1

        total_snaps = max(len(snapshots), 1)
        category_breakdown = {k: round(v * CAPTURE_INTERVAL) for k, v in category_counts.items()}
        productive_pct = round((productive_count / total_snaps) * 100)

        # Most common screen_title in this window
        from collections import Counter
        titles = [s.get("screen_title", "") for s in snapshots if s.get("screen_title")]
        top_title = Counter(titles).most_common(1)[0][0] if titles else ""

        return {
            "id": uid("win"),
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "window_label": f"{window_start.strftime('%Y-%m-%d %H:%M')} – {window_end.strftime('%H:%M')}",
            "date": window_start.strftime("%Y-%m-%d"),
            "snapshot_count": len(snapshots),
            "narrative": synthesis.get("narrative", ""),
            "primary_activity": synthesis.get("primary_activity", ""),
            "apps_used": synthesis.get("apps_used", []),
            "urls_visited": synthesis.get("urls_visited", []),
            "files_open": synthesis.get("files_open", []),
            "key_topics": synthesis.get("key_topics", []),
            "entities": dict(merged_entities),
            "category_breakdown": dict(category_breakdown),
            "productive_pct": productive_pct,
            "top_title": top_title,
        }

    def process_window(self, window_start: datetime):
        """
        Drain the buffer, synthesize, persist. Called by the summary loop.
        Thread safe: drains buffer under _buffer_lock, writes under _file_lock.
        """
        global _raw_buffer

        window_end = window_start + timedelta(minutes=SUMMARY_INTERVAL)

        # ── Atomically drain the buffer ───────────────────────────────────────
        with _buffer_lock:
            # Take only snapshots that belong to this window
            # (clock-aligned: any snapshot timestamped before window_end)
            to_process = [s for s in _raw_buffer
                          if datetime.fromisoformat(s["_ts"]) < window_end]
            _raw_buffer = [s for s in _raw_buffer
                           if datetime.fromisoformat(s["_ts"]) >= window_end]

        if not to_process:
            return

        # ── Synthesize (Groq call, no lock held) ──────────────────────────────
        window_entry = self.synthesize_window(to_process, window_start, window_end)
        if not window_entry:
            return

        # ── Persist summary + upsert entities ─────────────────────────────────
        with _file_lock:
            summaries = load_json(SUMMARIES_FILE, [])
            summaries.append(window_entry)
            save_json_async(SUMMARIES_FILE, summaries)

            self.memory._upsert_entities(
                window_entry["entities"],
                window_start
            )

    def run_loop(self):
        """
        Clock-aligned summary loop.
        Sleeps until the next window boundary, then processes the just-closed window.
        """
        while True:
            try:
                sleep_secs = seconds_until_next_window()
                time.sleep(max(sleep_secs, 1))

                closed_window_start = current_window_start() - timedelta(minutes=SUMMARY_INTERVAL)
                self.process_window(closed_window_start)

            except KeyboardInterrupt:
                break
            except Exception as e:
                time.sleep(10)


# ══════════════════════════════════════════════════════════════════════════════
# Agent 3 — MemoryAgent
# Pure JSON. Thread-safe reads/writes. Keyword retrieval. Entity upsert.
# ══════════════════════════════════════════════════════════════════════════════

class MemoryAgent:

    def __init__(self):
        self.chat_history = []
        self._recover_orphans()

    def _recover_orphans(self):
        """On startup, recover any snapshots that weren't summarized before shutdown."""
        global _raw_buffer
        if ORPHAN_FILE.exists():
            try:
                orphans = load_json(ORPHAN_FILE, [])
                if orphans:
                    with _buffer_lock:
                        _raw_buffer.extend(orphans)
                ORPHAN_FILE.unlink()
            except Exception:
                pass

    def save_orphans(self):
        """Called on shutdown to persist unprocessed buffer snapshots."""
        with _buffer_lock:
            if _raw_buffer:
                ORPHAN_FILE.write_text(json.dumps(_raw_buffer, indent=2, default=str))

    # ── Push a snapshot into the in-memory buffer ─────────────────────────────

    def push_snapshot(self, reading: dict):
        """Thread-safe append to raw buffer. Called by screenshot loop."""
        with _buffer_lock:
            _raw_buffer.append(reading)

    # ── Smart entity upsert ───────────────────────────────────────────────────
    # Called by SummaryAgent under _file_lock — do NOT acquire _file_lock here.

    def _upsert_entities(self, entities: dict, now: datetime):
        db = load_json(ENTITIES_FILE, {
            "deadlines": [], "job_applications": [], "links": [],
            "research": [], "people": [], "projects": []
        })

        STATUS_RANK = {"saved": 0, "applied": 1, "interviewing": 2, "offered": 3, "rejected": 3}

        # Deadlines
        for d in entities.get("deadlines", []):
            if not d.get("title"):
                continue
            existing = next((x for x in db["deadlines"]
                             if x["title"].lower() == d["title"].lower()), None)
            if existing:
                if d.get("due_date"):
                    existing["due_date"] = d["due_date"]
                existing["last_seen"] = now.isoformat()
            else:
                db["deadlines"].append({
                    "id": uid("dl"), "title": d["title"],
                    "due_date": d.get("due_date"), "notes": d.get("notes"),
                    "created": now.isoformat(), "last_seen": now.isoformat(),
                    "done": False
                })

        # Job applications
        for j in entities.get("job_applications", []):
            if not j.get("company"):
                continue
            existing = next((x for x in db["job_applications"]
                             if x["company"].lower() == j["company"].lower()), None)
            if existing:
                new_rank = STATUS_RANK.get(j.get("status", ""), 0)
                old_rank = STATUS_RANK.get(existing["status"], 0)
                if new_rank > old_rank:
                    existing["status"] = j["status"]
                existing["last_seen"] = now.isoformat()
            else:
                db["job_applications"].append({
                    "id": uid("job"), "company": j["company"],
                    "role": j.get("role"), "status": j.get("status", "saved"),
                    "date_first_seen": now.strftime("%Y-%m-%d"),
                    "last_seen": now.isoformat()
                })

        # Links
        for lnk in entities.get("links", []):
            if not lnk.get("url"):
                continue
            existing = next((x for x in db["links"] if x["url"] == lnk["url"]), None)
            if existing:
                existing["last_visited"] = now.isoformat()
            else:
                db["links"].append({
                    "id": uid("lnk"), "url": lnk["url"],
                    "title": lnk.get("title"), "topic": lnk.get("topic"),
                    "first_visited": now.isoformat(), "last_visited": now.isoformat()
                })

        # Research
        for r in entities.get("research_topics", []):
            if not r.get("topic"):
                continue
            existing = next((x for x in db["research"]
                             if x["topic"].lower() == r["topic"].lower()), None)
            if existing:
                existing["last_seen"] = now.isoformat()
                if r.get("summary"):
                    existing["summary"] = r["summary"]
            else:
                db["research"].append({
                    "id": uid("res"), "topic": r["topic"],
                    "summary": r.get("summary"),
                    "first_seen": now.strftime("%Y-%m-%d"),
                    "last_seen": now.isoformat()
                })

        # People
        for p in entities.get("people", []):
            if not p.get("name"):
                continue
            existing = next((x for x in db["people"]
                             if x["name"].lower() == p["name"].lower()), None)
            if not existing:
                db["people"].append({
                    "id": uid("ppl"), "name": p["name"],
                    "context": p.get("context"),
                    "first_seen": now.isoformat(), "last_seen": now.isoformat()
                })
            else:
                existing["last_seen"] = now.isoformat()
                if p.get("context") and not existing.get("context"):
                    existing["context"] = p["context"]

        # Projects
        for proj in entities.get("projects", []):
            if not proj:
                continue
            existing = next((x for x in db["projects"]
                             if x["name"].lower() == proj.lower()), None)
            if existing:
                existing["last_seen"] = now.isoformat()
                existing["total_mins"] = existing.get("total_mins", 0) + SUMMARY_INTERVAL
            else:
                db["projects"].append({
                    "id": uid("prj"), "name": proj,
                    "first_seen": now.isoformat(), "last_seen": now.isoformat(),
                    "total_mins": SUMMARY_INTERVAL
                })

        save_json_async(ENTITIES_FILE, db)

    # ── Keyword retrieval ─────────────────────────────────────────────────────

    def keyword_search_summaries(self, query: str, max_results: int = 10) -> list:
        """
        For-loop keyword search over window summaries.
        Scores each window by how many query tokens appear in its text fields.
        Returns top N results sorted by score descending.
        """
        tokens = set(query.lower().split())
        summaries = load_json(SUMMARIES_FILE, [])
        scored = []

        for w in summaries:
            # Build a searchable text blob for this window
            blob = " ".join([
                w.get("narrative", ""),
                w.get("primary_activity", ""),
                " ".join(w.get("apps_used", [])),
                " ".join(w.get("urls_visited", [])),
                " ".join(w.get("files_open", [])),
                " ".join(w.get("key_topics", [])),
                # also search into entities
                str(w.get("entities", {}))
            ]).lower()

            score = sum(1 for t in tokens if t in blob)
            if score > 0:
                scored.append((score, w))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [w for _, w in scored[:max_results]]

    def time_filter_summaries(self, hour: int = None, date_str: str = None) -> list:
        """Filter summaries by hour (e.g. 14 for 2pm) or date string (YYYY-MM-DD)."""
        summaries = load_json(SUMMARIES_FILE, [])
        results = []
        for w in summaries:
            ws = datetime.fromisoformat(w["window_start"])
            if date_str and w.get("date") != date_str:
                continue
            if hour is not None and ws.hour != hour:
                continue
            results.append(w)
        return results

    # ── Build context for chat ────────────────────────────────────────────────

    def _build_context(self, query: str) -> str:
        parts = []
        query_lower = query.lower()

        # ── Time detection: "at 2pm", "at 14:00", "this morning", "yesterday" ─
        hour_filter = None
        date_filter = None
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        time_patterns = [
            (r'\b(\d{1,2})\s*pm\b', lambda m: int(m.group(1)) + 12 if int(m.group(1)) != 12 else 12),
            (r'\b(\d{1,2})\s*am\b', lambda m: int(m.group(1)) if int(m.group(1)) != 12 else 0),
            (r'\b(\d{1,2}):(\d{2})\b', lambda m: int(m.group(1))),
        ]
        for pattern, extractor in time_patterns:
            m = re.search(pattern, query_lower)
            if m:
                hour_filter = extractor(m)
                break

        if "yesterday" in query_lower:
            date_filter = yesterday
        elif any(w in query_lower for w in ["today", "this morning", "this afternoon", "tonight"]):
            date_filter = today

        # ── Relevant window summaries ──────────────────────────────────────────
        if hour_filter is not None or date_filter is not None:
            windows = self.time_filter_summaries(hour=hour_filter, date_str=date_filter)
            label = f"hour={hour_filter}" if hour_filter else f"date={date_filter}"
            if windows:
                parts.append(f"=== ACTIVITY WINDOWS MATCHING [{label}] ===")
                for w in windows:
                    parts.append(self._format_window(w))
        else:
            # Keyword search
            windows = self.keyword_search_summaries(query, max_results=8)
            if windows:
                parts.append("=== RELEVANT ACTIVITY WINDOWS ===")
                for w in windows:
                    parts.append(self._format_window(w))

        # ── Also show recent windows for context ───────────────────────────────
        all_summaries = load_json(SUMMARIES_FILE, [])
        recent = all_summaries[-5:] if all_summaries else []
        if recent:
            parts.append("\n=== MOST RECENT WINDOWS ===")
            for w in recent:
                parts.append(self._format_window(w, brief=True))

        # ── In-flight snapshots (buffer, not yet summarized) ───────────────────
        with _buffer_lock:
            buffer_copy = list(_raw_buffer)
        if buffer_copy:
            parts.append(f"\n=== IN-PROGRESS WINDOW (last {len(buffer_copy)} snapshots, not yet summarized) ===")
            for s in buffer_copy[-5:]:
                parts.append(f"[{s.get('_time','?')}] {s.get('app','?')}: {s.get('summary','')}")

        # ── Structured entities ────────────────────────────────────────────────
        db = load_json(ENTITIES_FILE, {})

        if db.get("deadlines"):
            parts.append("\n=== DEADLINES & TASKS ===")
            for d in db["deadlines"]:
                status = "✅ done" if d.get("done") else f"due: {d.get('due_date') or 'no date set'}"
                line = f"- {d['title']} | {status}"
                if d.get("notes"):
                    line += f" | {d['notes']}"
                parts.append(line)

        if db.get("job_applications"):
            parts.append("\n=== JOB APPLICATIONS ===")
            for j in db["job_applications"]:
                parts.append(
                    f"- {j['company']} | {j.get('role') or 'role unknown'} | "
                    f"status: {j['status']} | first seen: {j['date_first_seen']}"
                )

        if db.get("links"):
            parts.append("\n=== SAVED LINKS ===")
            for lnk in db["links"][-30:]:
                parts.append(
                    f"- [{lnk.get('topic','?')}] {lnk.get('title','untitled')} "
                    f"| {lnk['url']} | visited: {lnk['last_visited'][:16]}"
                )

        if db.get("research"):
            parts.append("\n=== RESEARCH TOPICS ===")
            for r in db["research"]:
                parts.append(f"- {r['topic']}: {r.get('summary','')} | last: {r['last_seen'][:10]}")

        if db.get("people"):
            parts.append("\n=== PEOPLE ===")
            for p in db["people"]:
                parts.append(f"- {p['name']}: {p.get('context','')} | first seen: {p['first_seen'][:10]}")

        if db.get("projects"):
            parts.append("\n=== PROJECTS ===")
            for p in db["projects"]:
                parts.append(
                    f"- {p['name']} | {p.get('total_mins',0)} mins | "
                    f"last seen: {p['last_seen'][:16]}"
                )

        return "\n".join(parts) if parts else "No memories recorded yet. Start the watcher to build memory."

    def _format_window(self, w: dict, brief: bool = False) -> str:
        line = f"[{w['window_label']}] {w.get('narrative', '')}"
        if not brief:
            if w.get("apps_used"):
                line += f"\n  apps: {', '.join(w['apps_used'])}"
            if w.get("urls_visited"):
                line += f"\n  urls: {', '.join(w['urls_visited'][:5])}"
            if w.get("key_topics"):
                line += f"\n  topics: {', '.join(w['key_topics'])}"
        return line

    # ── Chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_message: str) -> str:
        context = self._build_context(user_message)

        system = f"""You are Luke, a personal AI second brain.
You watch the user's screen every {CAPTURE_INTERVAL} seconds and summarize activity in {SUMMARY_INTERVAL}-minute windows.

Current time: {datetime.now().strftime("%Y-%m-%d %H:%M")}

Here is everything you remember:
{context}

Answer naturally and specifically. Include exact times, window ranges, company names, and URLs when available.
If something isn't in memory, say so honestly — don't guess.
For deadlines, flag anything coming up soon.
Keep answers helpful and concise."""

        self.chat_history.append({"role": "user", "content": user_message})
        messages = [{"role": "system", "content": system}] + self.chat_history[-10:]
        response = groq_text(messages)
        self.chat_history.append({"role": "assistant", "content": response})
        return response


# ══════════════════════════════════════════════════════════════════════════════
# TaskAgent
# Two sources: /task command (explicit) + screen scraping (passive).
# Both write to tasks.json with identical schema.
# Dedup runs on every write — fuzzy title match prevents duplicates.
# ══════════════════════════════════════════════════════════════════════════════

class TaskAgent:

    STATUS_PENDING   = "pending"
    STATUS_DONE      = "done"
    SOURCE_USER      = "user"       # explicit /task command
    SOURCE_SCREEN    = "screen"     # passive screen scraping

    # ── Fuzzy dedup: are two task titles similar enough to be the same? ───────
    @staticmethod
    def _similar(a: str, b: str) -> bool:
        a, b = a.lower().strip(), b.lower().strip()
        if a == b:
            return True
        # one is a substring of the other (catches "follow up Angela" vs "follow up with Angela Truong")
        if a in b or b in a:
            return True
        # word overlap > 60%
        wa, wb = set(a.split()), set(b.split())
        if not wa or not wb:
            return False
        overlap = len(wa & wb) / max(len(wa), len(wb))
        return overlap >= 0.6

    def _load(self) -> list:
        return load_json(TASKS_FILE, [])

    def _save(self, tasks: list):
        save_json_async(TASKS_FILE, tasks)

    # ── Enrich with people context from entities.json ─────────────────────────
    @staticmethod
    def _enrich_context(title: str) -> str:
        entities = load_json(ENTITIES_FILE, {})
        for person in entities.get("people", []):
            name = person.get("name", "")
            # if person's first name appears in the task title, add their context
            first = name.split()[0].lower() if name else ""
            if first and first in title.lower() and person.get("context"):
                return f"{name} — {person['context']}"
        return ""

    # ── Parse due date from natural language ──────────────────────────────────
    @staticmethod
    def _parse_due(text: str) -> str | None:
        text = text.lower()
        today = datetime.now()
        if "today" in text:
            return today.strftime("%Y-%m-%d")
        if "tomorrow" in text:
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")
        if "next week" in text:
            return (today + timedelta(weeks=1)).strftime("%Y-%m-%d")
        # "by friday", "on monday" etc
        days = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
        for i, day in enumerate(days):
            if day in text:
                current_dow = today.weekday()
                target_dow  = i
                delta = (target_dow - current_dow) % 7 or 7
                return (today + timedelta(days=delta)).strftime("%Y-%m-%d")
        # explicit YYYY-MM-DD
        m = re.search(r"\d{4}-\d{2}-\d{2}", text)
        if m:
            return m.group(0)
        return None

    # ── Add a task (called from /task command or screen scrape) ───────────────
    def add(self, title: str, due_date: str = None, priority: str = "normal",
            source: str = SOURCE_USER, source_detail: str = "") -> dict:
        title = title.strip()
        if not title:
            return None

        # parse due from title if not provided
        if not due_date:
            due_date = self._parse_due(title)
            # strip due-date phrase from title
            title = re.sub(
                r"\b(by |on )?(today|tomorrow|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
                "", title, flags=re.IGNORECASE
            ).strip(" ,")

        with _file_lock:
            tasks = self._load()

            # dedup check
            for existing in tasks:
                if existing["status"] == self.STATUS_PENDING and self._similar(existing["title"], title):
                    return {"duplicate": True, "task": existing}

            person_context = self._enrich_context(title)

            task = {
                "id":             uid("task"),
                "title":          title,
                "due_date":       due_date,
                "priority":       priority if priority in ("high","normal","low") else "normal",
                "status":         self.STATUS_PENDING,
                "source":         source,
                "source_detail":  source_detail,
                "person_context": person_context,
                "created":        datetime.now().isoformat(),
                "completed_at":   None,
            }
            tasks.append(task)
            self._save(tasks)
            return {"duplicate": False, "task": task}

    # ── Ingest tasks found by ScreenReaderAgent ───────────────────────────────
    def ingest_from_screen(self, screen_tasks: list, snapshot_time: str, app: str):
        for t in screen_tasks:
            title = t.get("title", "").strip()
            if not title:
                continue
            self.add(
                title        = title,
                due_date     = t.get("due_date"),
                priority     = t.get("priority", "normal"),
                source       = self.SOURCE_SCREEN,
                source_detail= f"{app} — seen at {snapshot_time}",
            )

    # ── List tasks ────────────────────────────────────────────────────────────
    def list_tasks(self, status: str = None, include_done: bool = False) -> list:
        tasks = self._load()
        if not include_done:
            tasks = [t for t in tasks if t["status"] == self.STATUS_PENDING]
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        # sort: high priority first, then by due date
        priority_rank = {"high": 0, "normal": 1, "low": 2}
        tasks.sort(key=lambda t: (
            priority_rank.get(t.get("priority","normal"), 1),
            t.get("due_date") or "9999"
        ))
        return tasks

    # ── Complete a task by index (1-based) or partial title match ─────────────
    def complete(self, identifier: str) -> dict | None:
        with _file_lock:
            tasks = self._load()
            pending = [t for t in tasks if t["status"] == self.STATUS_PENDING]

            target = None
            # try numeric index first
            if identifier.strip().isdigit():
                idx = int(identifier.strip()) - 1
                if 0 <= idx < len(pending):
                    target = pending[idx]
            else:
                # fuzzy title match
                for t in pending:
                    if self._similar(t["title"], identifier):
                        target = t
                        break

            if not target:
                return None

            for t in tasks:
                if t["id"] == target["id"]:
                    t["status"]       = self.STATUS_DONE
                    t["completed_at"] = datetime.now().isoformat()
                    break

            self._save(tasks)
            return target

    # ── Remove a task permanently ─────────────────────────────────────────────
    def remove(self, identifier: str) -> dict | None:
        with _file_lock:
            tasks = self._load()
            target = None
            if identifier.strip().startswith("task_"):
                # match by id
                target = next((t for t in tasks if t["id"] == identifier.strip()), None)
            else:
                # fuzzy title match
                for t in tasks:
                    if self._similar(t["title"], identifier):
                        target = t
                        break
            if not target:
                return None
            tasks = [t for t in tasks if t["id"] != target["id"]]
            self._save(tasks)
            return target
    def format_for_chat(self, tasks: list) -> str:
        if not tasks:
            return "No pending tasks."
        lines = []
        for i, t in enumerate(tasks, 1):
            due  = f" · due {t['due_date']}" if t.get("due_date") else ""
            pri  = " 🔴" if t.get("priority") == "high" else ""
            src  = " [screen]" if t.get("source") == "screen" else ""
            ctx  = f" ({t['person_context']})" if t.get("person_context") else ""
            lines.append(f"{i}. {t['title']}{ctx}{due}{pri}{src}")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# CategoryTracker — separate SQLite DB for productivity/screen-time tracking
# Writes per-screenshot category data, aggregates into hourly + daily summaries.
# Completely separate from superluke JSON files.
# ══════════════════════════════════════════════════════════════════════════════

import sqlite3

PROD_DB_PATH = str(MEMORY_DIR / "productivity.db")

CATEGORY_PRODUCTIVE = {
    "coding", "writing", "learning", "research",
    "email", "meeting", "ai_tools", "design", "productivity_tools"
}
CATEGORY_NEUTRAL      = {"job_search", "communication", "browsing"}
CATEGORY_UNPRODUCTIVE = {"youtube_video", "social_media", "gaming", "distraction"}


class CategoryTracker:
    """
    Receives one reading per screenshot and writes to productivity.db.
    Three tables:
      screen_events  — one row per screenshot (raw log)
      category_time  — seconds per category per day (running totals)
      hourly_scores  — avg productivity score per hour per day
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(PROD_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS screen_events (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                ts               TEXT NOT NULL,
                date             TEXT NOT NULL,
                hour             INTEGER NOT NULL,
                app              TEXT,
                screen_title     TEXT,
                screen_category  TEXT,
                productive       INTEGER,
                productivity_score REAL,
                url              TEXT
            );

            CREATE TABLE IF NOT EXISTS category_time (
                date             TEXT NOT NULL,
                screen_category  TEXT NOT NULL,
                total_seconds    INTEGER DEFAULT 0,
                PRIMARY KEY (date, screen_category)
            );

            CREATE TABLE IF NOT EXISTS hourly_scores (
                date             TEXT NOT NULL,
                hour             INTEGER NOT NULL,
                avg_score        REAL,
                sample_count     INTEGER DEFAULT 0,
                dominant_category TEXT,
                PRIMARY KEY (date, hour)
            );
        """)
        conn.commit()
        conn.close()

    # ── Called per screenshot ─────────────────────────────────────────────────

    def record(self, reading: dict):
        """Thread-safe. Called from screenshot_loop for every new reading."""
        ts       = reading.get("_ts", datetime.now().isoformat())
        date     = reading.get("_date", datetime.now().strftime("%Y-%m-%d"))
        hour     = datetime.fromisoformat(ts).hour
        cat      = reading.get("screen_category", "other")
        prod_score = None
        p = reading.get("_productivity", {})
        if p:
            prod_score = p.get("productivity_score")

        with self._lock:
            conn = self._conn()
            try:
                # 1. raw event
                conn.execute("""
                    INSERT INTO screen_events
                      (ts, date, hour, app, screen_title, screen_category, productive, productivity_score, url)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (
                    ts, date, hour,
                    reading.get("app"),
                    reading.get("screen_title"),
                    cat,
                    1 if reading.get("productive") else 0,
                    prod_score,
                    reading.get("url"),
                ))

                # 2. upsert category_time (+CAPTURE_INTERVAL seconds)
                conn.execute("""
                    INSERT INTO category_time (date, screen_category, total_seconds)
                    VALUES (?, ?, ?)
                    ON CONFLICT(date, screen_category)
                    DO UPDATE SET total_seconds = total_seconds + excluded.total_seconds
                """, (date, cat, CAPTURE_INTERVAL))

                # 3. upsert hourly_scores (running average)
                if prod_score is not None:
                    existing = conn.execute(
                        "SELECT avg_score, sample_count FROM hourly_scores WHERE date=? AND hour=?",
                        (date, hour)
                    ).fetchone()
                    if existing:
                        new_count = existing["sample_count"] + 1
                        new_avg   = ((existing["avg_score"] * existing["sample_count"]) + prod_score) / new_count
                        conn.execute("""
                            UPDATE hourly_scores SET avg_score=?, sample_count=?, dominant_category=?
                            WHERE date=? AND hour=?
                        """, (round(new_avg, 2), new_count, cat, date, hour))
                    else:
                        conn.execute("""
                            INSERT INTO hourly_scores (date, hour, avg_score, sample_count, dominant_category)
                            VALUES (?,?,?,1,?)
                        """, (date, hour, round(prod_score, 2), cat))

                conn.commit()
            finally:
                conn.close()

    # ── Query helpers for /productivity/report ────────────────────────────────

    def get_today_summary(self) -> dict:
        date = datetime.now().strftime("%Y-%m-%d")
        conn = self._conn()
        try:
            # category breakdown for today
            cats = conn.execute(
                "SELECT screen_category, total_seconds FROM category_time WHERE date=? ORDER BY total_seconds DESC",
                (date,)
            ).fetchall()

            # hourly scores
            hours = conn.execute(
                "SELECT hour, avg_score, dominant_category FROM hourly_scores WHERE date=? ORDER BY hour",
                (date,)
            ).fetchall()

            # recent screen events (last 20)
            events = conn.execute(
                "SELECT ts, screen_title, screen_category, productive FROM screen_events WHERE date=? ORDER BY id DESC LIMIT 20",
                (date,)
            ).fetchall()

            cat_data = [{"category": r["screen_category"], "seconds": r["total_seconds"]} for r in cats]
            total_tracked = sum(r["total_seconds"] for r in cats)
            productive_secs = sum(
                r["total_seconds"] for r in cats
                if r["screen_category"] in CATEGORY_PRODUCTIVE
            )
            unproductive_secs = sum(
                r["total_seconds"] for r in cats
                if r["screen_category"] in CATEGORY_UNPRODUCTIVE
            )

            return {
                "date": date,
                "total_tracked_seconds": total_tracked,
                "productive_seconds": productive_secs,
                "unproductive_seconds": unproductive_secs,
                "neutral_seconds": total_tracked - productive_secs - unproductive_secs,
                "productive_pct": round((productive_secs / max(total_tracked, 1)) * 100),
                "category_breakdown": cat_data,
                "hourly_scores": [dict(r) for r in hours],
                "recent_events": [dict(r) for r in events],
            }
        finally:
            conn.close()

    def get_category_report(self, days: int = 7) -> list:
        """Returns per-category totals over last N days."""
        conn = self._conn()
        try:
            rows = conn.execute("""
                SELECT screen_category,
                       SUM(total_seconds) as total_seconds,
                       COUNT(DISTINCT date) as days_seen
                FROM category_time
                WHERE date >= date('now', ?)
                GROUP BY screen_category
                ORDER BY total_seconds DESC
            """, (f"-{days} days",)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# Screenshot Loop
# Polls every CAPTURE_INTERVAL seconds. Only calls vision when screen changes.
# Pushes results directly into in-memory buffer (thread-safe via _buffer_lock).
# ══════════════════════════════════════════════════════════════════════════════

def screenshot_loop(memory: MemoryAgent, task_agent: "TaskAgent" = None,
                    productivity_tracker=None, category_tracker: "CategoryTracker" = None):
    reader = ScreenReaderAgent()
    prev   = None

    while True:
        try:
            now = datetime.now()
            img = take_screenshot()

            if prev is not None and not images_are_different(prev, img):
                time.sleep(CAPTURE_INTERVAL)
                continue

            reading = reader.read(img, now)

            # ── Attach live productivity snapshot ─────────────────────────────
            if productivity_tracker:
                reading["_productivity"] = productivity_tracker.get_snapshot()

            memory.push_snapshot(reading)

            # ── Record to productivity SQLite DB ──────────────────────────────
            if category_tracker:
                category_tracker.record(reading)

            # ── Passive task ingestion from screen ────────────────────────────
            if task_agent:
                screen_tasks = reading.get("entities", {}).get("tasks", [])
                if screen_tasks:
                    task_agent.ingest_from_screen(
                        screen_tasks,
                        snapshot_time = now.strftime("%H:%M"),
                        app           = reading.get("app", "unknown"),
                    )

            prev = img
            time.sleep(CAPTURE_INTERVAL)

        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(CAPTURE_INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
# Chat Loop
# ══════════════════════════════════════════════════════════════════════════════

def chat_loop(memory: MemoryAgent):
    print("\n" + "="*60)
    print("  🧠 Luke Superluke — your second brain")
    print(f"  📸 Screenshots every {CAPTURE_INTERVAL}s | 🪟 Windows every {SUMMARY_INTERVAL} min")
    print()
    print("  Try asking:")
    print("    what was I working on at 2pm?")
    print("    list all the companies I applied to")
    print("    do I have any upcoming deadlines?")
    print("    what research did I do about vector databases?")
    print("    what links did I open about LLMs today?")
    print("    what resume did I have open last Tuesday?")
    print("    who is Sarah from the email I saw?")
    print()
    print("  'quit' to exit")
    print("="*60 + "\n")

    while True:
        try:
            user_input = input("  You > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("  Luke: See you! 👋")
                break

            response = memory.chat(user_input)
            print(f"\n  Luke: {response}\n")

        except KeyboardInterrupt:
            print("\n  Luke: Bye!")
            break


# ══════════════════════════════════════════════════════════════════════════════
# Entry
# ══════════════════════════════════════════════════════════════════════════════

def main():
    _start_writer()
    memory             = MemoryAgent()
    summary            = SummaryAgent(memory)
    task_agent         = TaskAgent()
    category_tracker   = CategoryTracker()
    cmd                = sys.argv[1] if len(sys.argv) > 1 else "both"

    try:
        from productivity import DeviceTracker
        productivity_tracker = DeviceTracker()
        productivity_tracker.start()
    except Exception:
        productivity_tracker = None

    def _shutdown(sig, frame):
        memory.save_orphans()
        if productivity_tracker:
            productivity_tracker.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    if cmd == "watch":
        t = threading.Thread(target=summary.run_loop, daemon=True)
        t.start()
        screenshot_loop(memory, task_agent, productivity_tracker, category_tracker)

    elif cmd == "chat":
        chat_loop(memory)

    else:
        t_screen  = threading.Thread(
            target=screenshot_loop,
            args=(memory, task_agent, productivity_tracker, category_tracker),
            daemon=True
        )
        t_summary = threading.Thread(target=summary.run_loop, daemon=True)
        t_screen.start()
        t_summary.start()
        time.sleep(1)
        chat_loop(memory)
        memory.save_orphans()


if __name__ == "__main__":
    main()