# memory.py — agent remembers what worked and adapts next time

import json
import os
import time

MEMORY_FILE = "clr_memory.json"


class AgentMemory:
    """
    Persists intervention history so the agent can adapt its strategy.
    Tracks: what action was taken, did the user reopen distractions quickly,
    did score drop after intervention, time of day patterns.
    """

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "interventions": [],       # history of all actions taken
            "action_outcomes": {},     # action -> {"success": N, "fail": N}
            "reopened_quickly": 0,     # times user reopened distractions < 2min
            "total_rage_events": 0,
            "peak_hours": {},          # hour -> rage count
            "cooldown_override": 60,   # adapted cooldown in seconds
        }

    def _save(self):
        try:
            with open(MEMORY_FILE, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[MEMORY] save error: {e}")

    def record_intervention(self, action: str, score: int, zone: str):
        hour = str(time.localtime().tm_hour)
        entry = {
            "ts": time.time(),
            "action": action,
            "score": score,
            "zone": zone,
            "hour": hour,
            "score_after": None,   # filled in by observe()
            "reopened": False,
        }
        self.data["interventions"].append(entry)

        # track peak hours
        self.data["peak_hours"][hour] = self.data["peak_hours"].get(hour, 0) + 1

        if zone == "RAGE":
            self.data["total_rage_events"] += 1

        if action not in self.data["action_outcomes"]:
            self.data["action_outcomes"][action] = {"success": 0, "fail": 0}

        self._save()
        return len(self.data["interventions"]) - 1  # return index

    def observe_outcome(self, idx: int, score_after: int, reopened: bool):
        """Call ~2 min after intervention to record whether it worked."""
        if idx < 0 or idx >= len(self.data["interventions"]):
            return
        entry = self.data["interventions"][idx]
        entry["score_after"] = score_after
        entry["reopened"] = reopened

        action = entry["action"]
        if action in self.data["action_outcomes"]:
            if score_after < entry["score"] - 10 and not reopened:
                self.data["action_outcomes"][action]["success"] += 1
            else:
                self.data["action_outcomes"][action]["fail"] += 1

        if reopened:
            self.data["reopened_quickly"] += 1

        # adapt cooldown: if user keeps reopening, shorten cooldown (intervene faster)
        if self.data["reopened_quickly"] > 3:
            self.data["cooldown_override"] = max(30, self.data["cooldown_override"] - 10)
        
        self._save()

    def get_adapted_cooldown(self) -> int:
        return self.data.get("cooldown_override", 60)

    def get_best_action(self, zone: str) -> str | None:
        """
        If we have enough history, suggest the action that worked best
        for this zone — override Gemma if Gemma's choice has been failing.
        """
        outcomes = self.data["action_outcomes"]
        best = None
        best_ratio = 0.0

        for action, counts in outcomes.items():
            total = counts["success"] + counts["fail"]
            if total < 3:  # not enough data yet
                continue
            ratio = counts["success"] / total
            if ratio > best_ratio and ratio > 0.6:
                best_ratio = ratio
                best = action

        return best  # None means trust Gemma

    def get_peak_hour_warning(self) -> str | None:
        """Returns a voice warning if this is historically a bad hour."""
        hour = str(time.localtime().tm_hour)
        count = self.data["peak_hours"].get(hour, 0)
        if count >= 3:
            return f"Heads up — you tend to get overloaded around this time. Stay sharp."
        return None

    def summary(self) -> str:
        total = len(self.data["interventions"])
        rages = self.data["total_rage_events"]
        reopened = self.data["reopened_quickly"]
        outcomes = self.data["action_outcomes"]
        lines = [
            f"Total interventions: {total}",
            f"Rage events: {rages}",
            f"Times reopened distractions quickly: {reopened}",
            f"Adapted cooldown: {self.data['cooldown_override']}s",
        ]
        for action, c in outcomes.items():
            lines.append(f"  {action}: {c['success']} worked / {c['fail']} failed")
        return "\n".join(lines)