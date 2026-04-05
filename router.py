"""
router.py  —  Luna backend
==========================
Runs CLR agent + SuperMemory agents and serves the Electron UI.

    python router.py          → http://localhost:5000

python main.py (PyQt5 dashboard) is completely separate and unchanged.
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import threading, time, sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

app = Flask(__name__)
CORS(app)

# ══════════════════════════════════════════════════════════════════════════════
# SuperMemory agents
# ══════════════════════════════════════════════════════════════════════════════

from superluke import (
    _start_writer, MemoryAgent, SummaryAgent,
    TaskAgent, CategoryTracker, screenshot_loop,
)

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

threading.Thread(target=screenshot_loop,
    args=(memory, task_agent, productivity_tracker, category_tracker),
    daemon=True, name="mem-screen").start()
threading.Thread(target=summary.run_loop, daemon=True, name="mem-summary").start()
print("  🧠  SuperMemory agents started")

# ══════════════════════════════════════════════════════════════════════════════
# CLR agent  (vision + signals + voice)
# Runs as background threads — no PyQt5 needed here.
# If any dependency is missing the block is skipped gracefully.
# ══════════════════════════════════════════════════════════════════════════════

_clr_lock  = threading.Lock()
_clr_state = {
    "available":      False,
    "score":          0,
    "zone":           "NORMAL",
    "signals":        {},
    "log":            None,
    "focus_mode":     False,
    "stress_message": None,
    "stress_ts":      None,
    "last_updated":   None,
}
_clr_agent = None


def _clr_cb(data: dict):
    with _clr_lock:
        _clr_state["score"]        = data.get("score", 0)
        _clr_state["zone"]         = data.get("zone", "NORMAL")
        _clr_state["signals"]      = data.get("signals", {})
        _clr_state["log"]          = data.get("log") or _clr_state["log"]
        _clr_state["last_updated"] = datetime.now().isoformat()


class _Proxy:
    """Stand-in for CLRDashboard — stores stress messages for polling."""
    def notify_stress(self, msg: str):
        with _clr_lock:
            _clr_state["stress_message"] = msg
            _clr_state["stress_ts"]      = datetime.now().isoformat()
    def update_from_agent(self, data: dict):
        _clr_cb(data)


try:
    from vision_pipeline import VisionPipeline
    from agent import CLRAgent

    _vision    = VisionPipeline()
    _proxy     = _Proxy()
    _clr_agent = CLRAgent(ui_callback=_clr_cb, vision_pipeline=_vision, dashboard=_proxy)
    _clr_state["available"] = True

    threading.Thread(target=lambda: [
        (_clr_agent.set_vision_state(_vision.get_state()), time.sleep(2))
        for _ in iter(int, 1)
    ], daemon=True, name="clr-vision").start()

    threading.Thread(target=lambda: (
        __import__('voice_input').VoiceListener(
            on_stress_detected=_clr_agent.on_stress_detected
        ).start()
    ), daemon=True, name="clr-voice").start()

    _clr_agent.start()

    threading.Thread(target=lambda: (
        time.sleep(2),
        __import__('voice_output').speak_text(
            "CLR is running. Click focus when you're ready."
        )
    ), daemon=True, name="clr-greet").start()

    print("  🟢  CLR agent started (vision + voice + signals)")

except Exception as e:
    print(f"  ⚠️   CLR unavailable: {e}")

print("  🚀  Luna router → http://localhost:5000")

# ══════════════════════════════════════════════════════════════════════════════
# Routes — static
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return send_from_directory(os.path.dirname(__file__), "index.html")

# ══════════════════════════════════════════════════════════════════════════════
# Routes — SuperMemory
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/chat", methods=["POST"])
def chat():
    data    = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "no message"}), 400

    if message.lower().startswith("/task "):
        raw = message[6:].strip()
        priority = "normal"
        if "!high" in raw: priority = "high";  raw = raw.replace("!high","").strip()
        elif "!low" in raw: priority = "low";  raw = raw.replace("!low","").strip()
        result = task_agent.add(title=raw, priority=priority, source="user")
        if result.get("duplicate"):
            t = result["task"]
            return jsonify({"response": f"⚠️ Already tracked: **{t['title']}**", "type":"task_duplicate","task":t})
        t = result["task"]
        due = f" · due **{t['due_date']}**" if t.get("due_date") else ""
        return jsonify({"response": f"✅ Task saved: **{t['title']}**{due}", "type":"task_added","task":t})

    if message.lower().strip() in ("/tasks","list tasks","my tasks","show tasks"):
        tasks = task_agent.list_tasks()
        return jsonify({
            "response": "📋 **Your tasks:**\n" + task_agent.format_for_chat(tasks) if tasks else "📋 No pending tasks.",
            "type":"task_list","tasks":tasks,
        })

    if message.lower().startswith("/done "):
        completed = task_agent.complete(message[6:].strip())
        if completed:
            return jsonify({"response": f"✅ Done: **{completed['title']}**", "type":"task_done","task":completed})
        return jsonify({"response":"❌ Task not found.","type":"error"})

    return jsonify({"response": memory.chat(message), "type":"chat"})


@app.route("/tasks")
def list_tasks():
    include_done = request.args.get("include_done","false").lower() == "true"
    tasks = task_agent.list_tasks(include_done=include_done)
    return jsonify({"tasks": tasks, "count": len(tasks)})


@app.route("/task", methods=["POST"])
def add_task():
    d = request.get_json(silent=True) or {}
    return jsonify(task_agent.add(
        title=d.get("title",""), due_date=d.get("due_date"),
        priority=d.get("priority","normal"), source=d.get("source","user"),
        source_detail=d.get("source_detail",""),
    ))


@app.route("/task/done", methods=["POST"])
def complete_task():
    d   = request.get_json(silent=True) or {}
    res = task_agent.complete(d.get("id") or d.get("title",""))
    return jsonify({"ok":True,"task":res}) if res else (jsonify({"ok":False,"error":"not found"}),404)


@app.route("/task/remove", methods=["POST"])
def remove_task():
    d   = request.get_json(silent=True) or {}
    res = task_agent.remove(d.get("id") or d.get("title",""))
    return jsonify({"ok":True,"task":res}) if res else (jsonify({"ok":False,"error":"not found"}),404)


@app.route("/productivity")
def productivity():
    if not productivity_tracker:
        return jsonify({"error":"not available"}), 503
    return jsonify(productivity_tracker.get_snapshot())


@app.route("/productivity/report")
def productivity_report():
    return jsonify(category_tracker.get_today_summary())


@app.route("/productivity/categories")
def productivity_categories():
    days = int(request.args.get("days",7))
    return jsonify({"categories": category_tracker.get_category_report(days), "days":days})


@app.route("/status")
def status():
    from superluke import _raw_buffer, _buffer_lock, load_json, SUMMARIES_FILE, ENTITIES_FILE
    with _buffer_lock: buf = len(_raw_buffer)
    summaries = load_json(SUMMARIES_FILE, [])
    entities  = load_json(ENTITIES_FILE, {})
    tasks     = task_agent.list_tasks()
    prod      = productivity_tracker.get_snapshot() if productivity_tracker else {}
    return jsonify({
        "ok": True,
        "buffer_snapshots":   buf,
        "windows_summarized": len(summaries),
        "tasks_pending":      len(tasks),
        "productivity_score": prod.get("productivity_score"),
        "risk_level":         prod.get("risk_level"),
        "is_distracted":      prod.get("is_distracted", False),
    })

# ══════════════════════════════════════════════════════════════════════════════
# Routes — CLR
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/clr/status")
def clr_status():
    with _clr_lock:
        return jsonify(dict(_clr_state))


@app.route("/clr/focus", methods=["POST"])
def clr_focus():
    if not _clr_agent:
        return jsonify({"ok":False,"error":"CLR not running"}), 503
    enabled = (request.get_json(silent=True) or {}).get("enabled", True)
    _clr_agent.set_focus_mode(enabled)
    with _clr_lock: _clr_state["focus_mode"] = enabled
    return jsonify({"ok":True,"focus_mode":enabled})


@app.route("/clr/stress/ack", methods=["POST"])
def clr_stress_ack():
    with _clr_lock:
        _clr_state["stress_message"] = None
        _clr_state["stress_ts"]      = None
    return jsonify({"ok":True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
