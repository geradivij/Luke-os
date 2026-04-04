# import pyautogui
# import time
# from AppKit import NSScreen

# SCALE = NSScreen.mainScreen().backingScaleFactor()
# print(f"Scale factor: {SCALE}x")

# # USC folder is visible at top-right of screen
# # From screenshot: roughly x=1037, y=145 in logical points
# # (physical ~2074, 290 divided by scale 2.0)

# TARGET_X = 1037
# TARGET_Y = 145

# print(f"Moving to ({TARGET_X}, {TARGET_Y}) in 2 seconds...")
# print("Watch where the cursor goes!")
# time.sleep(2)

# pyautogui.moveTo(TARGET_X, TARGET_Y, duration=0.5)
# print(f"Cursor is now at ({TARGET_X}, {TARGET_Y})")
# print("Does it look right? (check cursor position on screen)")

# input("Press Enter to double-click, or Ctrl+C to abort > ")
# pyautogui.doubleClick()
# print("Clicked!")
# # import pyautogui
# # print(pyautogui.position())  # just print current cursor position
# # pyautogui.moveTo(500, 500, duration=1)

import pyautogui
import time
from AppKit import NSScreen

SCALE = NSScreen.mainScreen().backingScaleFactor()

x, y = 1037, 145  # start point

while True:
    pyautogui.moveTo(x, y, duration=0.2)
    cmd = input(f"  at ({x},{y}) — adjust? (w/a/s/d=5px, W/A/S/D=20px, c=click, q=quit) > ").strip()
    if cmd == 'q': break
    if cmd == 'c':
        pyautogui.doubleClick()
        break
    if cmd == 'w': y -= 5
    if cmd == 's': y += 5
    if cmd == 'a': x -= 5
    if cmd == 'd': x += 5
    if cmd == 'W': y -= 20
    if cmd == 'S': y += 20
    if cmd == 'A': x -= 20
    if cmd == 'D': x += 20
    print(f"  logical: ({x},{y}) | physical: ({x*SCALE:.0f},{y*SCALE:.0f})")