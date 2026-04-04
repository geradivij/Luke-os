import time
from signal_collector import SignalCollector
from load_score import LoadScoreEngine

sc = SignalCollector()
engine = LoadScoreEngine()

print("Testing load score... (alt-tab + backspace + then idle)")
for _ in range(12):
    time.sleep(5)
    s = sc.get_state()
    r = engine.compute(s)
    print(s, "=>", r)