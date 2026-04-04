from agent import CLRAgent
import time

agent = CLRAgent()
agent.set_focus_mode(True)
agent.start()

print("Agent running. Try alt-tab + backspace spam.")

while True:
    time.sleep(1)