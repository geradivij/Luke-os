"""
router.py
=========
Flask wrapper around superluke.py.
Exposes /chat, /task, /tasks, /task/done, /status, /

Run:
    pip install flask flask-cors
    python router.py
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from superluke import (
    _start_writer,
    MemoryAgent,
    SummaryAgent,
    TaskAgent,
    CategoryTracker,
    screenshot_loop,
)

app = Flask(__name__)
CORS(app)

# ── Boot all agents ────────────────────────────────────────────────────────
_start_writer()
memory           = MemoryAgent()
summary          = SummaryAgent(memory)
task_agent       = TaskAgent()
category_tracker = CategoryTracker()

try:
    from productivity import DeviceTracker
    productivity_tracker = DeviceTracker()
    productivity_tracker.start()
except Exception:
    productivity_tracker = None

t_screen  = threading.Thread(
    target=screenshot_loop,
    args=(memory, task_agent, productivity_tracker, category_tracker),
    daemon=True
)
t_summary = threading.Thread(target=summary.run_loop, daemon=True)
t_screen.start()
t_summary.start()

print("  🧠 Superluke router running on http://localhost:5000")
print("  👁  Screenshot + summary + task + productivity + category agents started")

# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return send_from_directory(os.path.dirname(__file__), "index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data    = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "no message"}), 400

    # ── /task command ──────────────────────────────────────────────────────
    if message.lower().startswith("/task "):
        raw = message[6:].strip()
        if not raw:
            return jsonify({"response": "Usage: /task <title> [by <date>] [!high]", "type": "error"})

        priority = "normal"
        if raw.endswith("!high") or raw.startswith("!high "):
            priority = "high"
            raw = raw.replace("!high", "").strip()
        elif raw.endswith("!low") or raw.startswith("!low "):
            priority = "low"
            raw = raw.replace("!low", "").strip()

        result = task_agent.add(title=raw, priority=priority, source="user")
        if result.get("duplicate"):
            t = result["task"]
            return jsonify({
                "response": f"⚠️ Already tracked: **{t['title']}**" + (f" · due {t['due_date']}" if t.get("due_date") else ""),
                "type": "task_duplicate",
                "task": t,
            })
        t = result["task"]
        due_str = f" · due **{t['due_date']}**" if t.get("due_date") else ""
        ctx_str = f"\n_{t['person_context']}_" if t.get("person_context") else ""
        return jsonify({
            "response": f"✅ Task saved: **{t['title']}**{due_str}{ctx_str}",
            "type": "task_added",
            "task": t,
        })

    # ── /tasks list ────────────────────────────────────────────────────────
    if message.lower().strip() in ("/tasks", "/task list", "list tasks", "my tasks", "what are my tasks", "show tasks"):
        tasks = task_agent.list_tasks()
        return jsonify({
            "response": "📋 **Your tasks:**\n" + task_agent.format_for_chat(tasks) if tasks else "📋 No pending tasks.",
            "type": "task_list",
            "tasks": tasks,
        })

    # ── /done command ──────────────────────────────────────────────────────
    if message.lower().startswith("/done "):
        identifier = message[6:].strip()
        completed  = task_agent.complete(identifier)
        if completed:
            return jsonify({
                "response": f"✅ Marked done: **{completed['title']}**",
                "type": "task_done",
                "task": completed,
            })
        return jsonify({"response": "❌ Task not found. Use /tasks to see your list.", "type": "error"})

    # ── normal memory chat ─────────────────────────────────────────────────
    response = memory.chat(message)
    return jsonify({"response": response, "type": "chat"})


@app.route("/tasks", methods=["GET"])
def list_tasks():
    include_done = request.args.get("include_done", "false").lower() == "true"
    tasks = task_agent.list_tasks(include_done=include_done)
    return jsonify({"tasks": tasks, "count": len(tasks)})


@app.route("/task", methods=["POST"])
def add_task():
    data = request.get_json(silent=True) or {}
    result = task_agent.add(
        title        = data.get("title", ""),
        due_date     = data.get("due_date"),
        priority     = data.get("priority", "normal"),
        source       = data.get("source", "user"),
        source_detail= data.get("source_detail", ""),
    )
    return jsonify(result)


@app.route("/task/done", methods=["POST"])
def complete_task():
    data       = request.get_json(silent=True) or {}
    identifier = data.get("id") or data.get("title") or ""
    completed  = task_agent.complete(identifier)
    if completed:
        return jsonify({"ok": True, "task": completed})
    return jsonify({"ok": False, "error": "not found"}), 404


@app.route("/task/remove", methods=["POST"])
def remove_task():
    data       = request.get_json(silent=True) or {}
    identifier = data.get("id") or data.get("title") or ""
    removed    = task_agent.remove(identifier)
    if removed:
        return jsonify({"ok": True, "task": removed})
    return jsonify({"ok": False, "error": "not found"}), 404


@app.route("/productivity", methods=["GET"])
def productivity():
    if not productivity_tracker:
        return jsonify({"error": "productivity tracker not available"}), 503
    return jsonify(productivity_tracker.get_snapshot())


@app.route("/productivity/report", methods=["GET"])
def productivity_report():
    """Today's full breakdown — category time, hourly scores, recent events."""
    return jsonify(category_tracker.get_today_summary())


@app.route("/productivity/categories", methods=["GET"])
def productivity_categories():
    """Per-category totals over last N days (default 7)."""
    days = int(request.args.get("days", 7))
    return jsonify({"categories": category_tracker.get_category_report(days), "days": days})


@app.route("/status", methods=["GET"])
def status():
    from superluke import _raw_buffer, _buffer_lock, load_json, SUMMARIES_FILE, ENTITIES_FILE
    with _buffer_lock:
        buf = len(_raw_buffer)
    summaries = load_json(SUMMARIES_FILE, [])
    entities  = load_json(ENTITIES_FILE, {})
    tasks     = task_agent.list_tasks()
    prod      = productivity_tracker.get_snapshot() if productivity_tracker else {}
    return jsonify({
        "ok":                True,
        "buffer_snapshots":  buf,
        "windows_summarized":len(summaries),
        "jobs_tracked":      len(entities.get("job_applications", [])),
        "people_tracked":    len(entities.get("people", [])),
        "links_tracked":     len(entities.get("links", [])),
        "tasks_pending":     len(tasks),
        "productivity_score": prod.get("productivity_score"),
        "risk_level":         prod.get("risk_level"),
        "is_distracted":      prod.get("is_distracted", False),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)