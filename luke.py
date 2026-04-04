import time
import json
import re
import os
import base64
import subprocess
from io import BytesIO

import mss
import pyautogui
from PIL import Image
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file or environment.")
groq_client  = Groq(api_key=GROQ_API_KEY)

VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"   # locate elements — best accuracy
FAST_MODEL   = "meta-llama/llama-4-scout-17b-16e-instruct"   # describe screen — faster

OPEN_BUFFER    = 2.5
DIFF_THRESHOLD = 0.02

OFFSET_X = -50
OFFSET_Y = 5
# ── Scale factor ──────────────────────────────────────────────────────────────

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
print(f"  [display] scale factor: {SCALE}x")
 
# ── Screenshot ────────────────────────────────────────────────────────────────
 
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
    max_dim = 1920
    if img.width > max_dim or img.height > max_dim:
        img = img.copy()
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
 
 
def groq_vision(img: Image.Image, prompt: str, model: str) -> str:
    response = groq_client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{pil_to_base64(img)}"}
                },
                {"type": "text", "text": prompt}
            ]
        }],
        max_tokens=1024,
        temperature=0.1
    )
    return response.choices[0].message.content.strip()
 
# ── Layer 1: Desktop icons via AppleScript ────────────────────────────────────
 
def get_desktop_icons() -> list[dict]:
    script = """
    tell application "Finder"
        set iconList to {}
        set desktopItems to every item of desktop
        repeat with i in desktopItems
            set iconPos to position of i
            set iconName to name of i
            set end of iconList to iconName & "|" & (item 1 of iconPos) & "|" & (item 2 of iconPos)
        end repeat
        return iconList
    end tell
    """
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
        icons = []
        for item in result.stdout.strip().split(", "):
            parts = item.strip().split("|")
            if len(parts) == 3:
                try:
                    x, y = float(parts[1]), float(parts[2])
                    if x == -1 and y == -1:
                        continue
                    icons.append({"name": parts[0].strip(), "x": x, "y": y, "source": "finder"})
                except ValueError:
                    continue
        return icons
    except Exception as e:
        print(f"  [warn] AppleScript failed: {e}")
        return []
 
 
def fuzzy_match_icon(target: str, icons: list[dict]) -> dict | None:
    t = target.lower().strip()
    for icon in icons:
        if t == icon["name"].lower():
            return icon
    for icon in icons:
        if t in icon["name"].lower() or icon["name"].lower() in t:
            return icon
    return None
 
# ── Layer 2: Open windows via Quartz ─────────────────────────────────────────
 
def get_window_list() -> list[dict]:
    try:
        import Quartz
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly |
            Quartz.kCGWindowListExcludeDesktopElements,
            Quartz.kCGNullWindowID
        )
        skip = {"Dock", "WindowServer", "SystemUIServer", "Control Center", "NotificationCenter"}
        result = []
        for w in windows:
            bounds = w.get("kCGWindowBounds", {})
            width  = bounds.get("Width", 0)
            height = bounds.get("Height", 0)
            owner  = w.get("kCGWindowOwnerName", "") or ""
            if width < 50 or height < 50 or owner in skip:
                continue
            result.append({
                "owner": owner,
                "name":  w.get("kCGWindowName", "") or "",
                "x":     max(0, bounds.get("X", 0)),
                "y":     max(0, bounds.get("Y", 0)),
                "w":     width,
                "h":     height,
                "source": "quartz"
            })
        return result
    except ImportError:
        print("  [warn] Quartz not available")
        return []
 
 
def fuzzy_match_window(target: str, windows: list[dict]) -> dict | None:
    t = target.lower().strip()
    for w in windows:
        if t == w["name"].lower() or t == w["owner"].lower():
            return w
    for w in windows:
        if t in w["name"].lower() or t in w["owner"].lower():
            return w
    return None
 
 
def window_center_logical(w: dict) -> tuple[float, float]:
    return (w["x"] + w["w"] / 2) / SCALE, (w["y"] + w["h"] / 2) / SCALE
 
# ── Layer 3: Two-step agentic vision loop ─────────────────────────────────────
 
def groq_find_agentic(
    img: Image.Image,
    target: str,
    windows: list[dict]
) -> tuple[float, float] | None:
    iw, ih = img.size
 
    # Build window context so model knows what regions belong to what
    window_map = "\n".join(
        f"  - '{w['owner']}' window (title: '{w['name']}'): "
        f"x={int(w['x']*SCALE)}-{int((w['x']+w['w'])*SCALE)}, "
        f"y={int(w['y']*SCALE)}-{int((w['y']+w['h'])*SCALE)}"
        for w in windows[:8]
    ) or "  none"
 
    # ── Step 1: Describe everything on screen ──
    step1_prompt = f"""You are analyzing a {iw}x{ih} screenshot of a macOS desktop.
 
Known open windows occupy these pixel regions:
{window_map}
 
Anything OUTSIDE those regions is the desktop (wallpaper + icons).
 
Carefully scan the ENTIRE image and list every visible UI element with its location:
- Every desktop icon (name + approximate pixel position of its center)
- Every visible window and what's inside it
- Dock items
- Menu bar items
 
Be specific about pixel positions. Format each item as:
  [type] name — center at (x, y)
 
Example:
  [desktop icon] USC — center at (2074, 290)
  [desktop icon] Downloads — center at (2074, 390)
  [window] VS Code — occupies (0,302) to (1722,1268)"""
 
    print("  [step 1] Mapping screen...")
    screen_map = groq_vision(img, step1_prompt, VISION_MODEL)
    print(f"  [step 1 result]\n{screen_map}\n")
 
    # ── Step 2: Find target in the map ──
    step2_prompt = f"""You previously described this {iw}x{ih} screenshot as:
 
{screen_map}
 
Based on that description, find: "{target}"
 
Rules:
- Use ONLY information from the description above
- Do not guess or hallucinate — if "{target}" was not mentioned, return found=false
- Return the pixel coordinates of the CENTER of the element in the full {iw}x{ih} image
 
Respond with ONLY JSON:
{{"x": 2074, "y": 290, "found": true, "label": "exact name from description"}}
 
If not found: {{"found": false}}
JSON only. No markdown."""
 
    print("  [step 2] Locating target in map...")
    raw = groq_vision(img, step2_prompt, VISION_MODEL)
    raw = re.sub(r"```json|```", "", raw).strip()
    print(f"  [step 2 result] {raw}")
 
    try:
        data = json.loads(raw)
        if not data.get("found"):
            return None
        px, py = int(data["x"]), int(data["y"])
        lx, ly = px / SCALE, py / SCALE
        print(f"  [agentic vision] '{data.get('label', target)}' at physical ({px},{py}) → logical ({lx:.0f},{ly:.0f})")
        return lx, ly
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"  [warn] parse failed: {e} | raw: {raw}")
        return None
 
# ── Screen description ────────────────────────────────────────────────────────
 
def describe_screen(img: Image.Image, windows: list[dict], icons: list[dict]) -> str:
    icon_names  = ", ".join(i["name"] for i in icons) or "none"
    win_summary = "\n".join(
        f"  - [{w['owner']}] '{w['name']}' ({int(w['w'])}x{int(w['h'])})"
        for w in windows[:10]
    ) or "  none"
 
    prompt = f"""Open windows:
{win_summary}
 
Desktop icons with known positions: {icon_names}
 
In 2 sentences describe what the user is currently looking at."""
 
    try:
        return groq_vision(img, prompt, FAST_MODEL)
    except Exception as e:
        return f"(description failed: {e})"
 
# ── Main loop ─────────────────────────────────────────────────────────────────
 
def main():
    print("=" * 60)
    print("  Luke — Screen Agent")
    print("  Finder → Quartz → Groq agentic vision (2-step)")
    print("  Type what to click. 'quit' to exit.")
    print("=" * 60)
 
    prev_screenshot = None
 
    while True:
        current_screenshot = take_screenshot()
        icons   = get_desktop_icons()
        windows = get_window_list()
 
        if prev_screenshot is not None:
            changed = images_are_different(prev_screenshot, current_screenshot)
            print(f"\n  [{'screen changed ✓' if changed else 'screen unchanged'}]")
 
        print("\n  Reading screen...\n")
        description = describe_screen(current_screenshot, windows, icons)
        print(f"  {description}")
 
        if icons:
            print(f"\n  DESKTOP ICONS (positioned): {', '.join(i['name'] for i in icons)}")
        if windows:
            print("\n  OPEN WINDOWS:")
            for w in windows[:10]:
                label = w['owner'] + (f" — {w['name']}" if w['name'] else "")
                print(f"    • {label}  [{int(w['w'])}x{int(w['h'])} at ({int(w['x'])},{int(w['y'])})]")
 
        user_input = input("\n  What should I click? > ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            print("  Bye!")
            break
        if not user_input:
            continue
 
        click_type = input("  Single or double click? (s/d, default=d) > ").strip().lower()
        do_double  = click_type != "s"
 
        lx = ly = None
        source = ""
 
        # Layer 1: Finder (exact)
        icon = fuzzy_match_icon(user_input, icons)
        if icon:
            lx, ly = icon["x"], icon["y"]
            source = f"finder '{icon['name']}'"
 
        # Layer 2: Quartz (exact)
        if lx is None:
            win = fuzzy_match_window(user_input, windows)
            if win:
                lx, ly = window_center_logical(win)
                source = f"quartz '{win['owner']}'"
 
        # Layer 3: Agentic two-step vision
        if lx is None:
            print(f"\n  Running agentic vision search for '{user_input}'...")
            coords = groq_find_agentic(current_screenshot, user_input, windows)
            if coords:
                lx, ly = coords
                source = "agentic vision"
 
        if lx is None:
            print(f"\n  ❌ Couldn't find '{user_input}'. Try rephrasing.")
            prev_screenshot = current_screenshot
            continue
 
        print(f"\n  ✅ [{source}] → ({lx:.0f}, {ly:.0f}) logical pts — clicking...")
        OFFSET_X = 45
        OFFSET_Y = -5
        final_x = lx + OFFSET_X
        final_y = ly + OFFSET_Y
        pyautogui.moveTo(final_x, final_y, duration=0.3)
        time.sleep(0.2)  # let it settle
        
        if do_double:
            pyautogui.click()
            time.sleep(0.3)
            pyautogui.click()
        else:
            pyautogui.click()
 
        print(f"  ⏳ Waiting {OPEN_BUFFER}s...")
        time.sleep(OPEN_BUFFER)
 
        prev_screenshot = current_screenshot
 
 
if __name__ == "__main__":
    main()