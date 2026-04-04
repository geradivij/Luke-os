# Luke (CLR Agent)

CLR is a local desktop focus assistant that monitors interaction signals, estimates cognitive load, and reacts with nudges/break overlays to reduce overload.

## What it does

- Collects behavior signals:
  - app switching frequency
  - backspace bursts
  - idle time
- Uses webcam vision to detect:
  - face presence
  - eye strain/closure
  - hand-on-face / hand-on-head stress gestures
- Computes a load score (0-100) and maps it to zones:
  - `NORMAL`, `ELEVATED`, `OVERLOAD`, `RAGE`
- Runs an agent loop that can:
  - start focus mode manually or auto-enable in stress conditions
  - choose interventions via local Gemma + LoRA adapter (with fallback rules)
  - execute actions like minimizing distracting apps, showing timed break overlays, and voice coaching
- Persists outcomes in `clr_memory.json` to adapt cooldowns and action preferences.

## Project structure

- `main.py`: app entrypoint (Qt app + vision + agent + dashboard + voice listener)
- `agent.py`: decision loop and intervention orchestration
- `signal_collector.py`: keyboard/mouse/window activity collection
- `vision_pipeline.py`: webcam + MediaPipe/CV signal extraction
- `load_score.py`: scoring and zone thresholds
- `action_executor.py`: minimize windows and display overlays
- `dashboard.py`: always-on-top control/status UI
- `memory.py`: persistent intervention memory
- `voice_input.py`: stress phrase listener
- `voice_output.py`: TTS feedback
- `gemma_decider_local.py`: local action-label inference using base Gemma + LoRA
- `finetune.py`: LoRA fine-tuning script
- `training_daya.py`: training examples generator (`training_data.py` header in file)

## Requirements

From `requirements.txt`:

- `transformers`, `datasets`, `peft`, `accelerate`, `trl`, `torch`
- `pynput`, `pygetwindow`
- `huggingface_hub`
- `opencv-python`, `mediapipe`
- `PyQt5`
- `pillow`

Optional but used by voice modules:

- `SpeechRecognition`
- `sounddevice` (fallback mic backend)
- `pyttsx3` (TTS)
- `PyAudio` (if using `SpeechRecognition` microphone backend directly)

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install SpeechRecognition sounddevice pyttsx3
```

If you want local Gemma inference/fine-tuning:

```powershell
$env:HF_TOKEN="hf_your_token_here"
```

## Run

```powershell
python main.py
```

Use the dashboard button to start focus mode. The agent then evaluates signals every ~2 seconds and intervenes when load is high.

## Model workflow (optional)

1. Prepare/adjust examples in `training_daya.py`.
2. Ensure the import expected by `finetune.py` resolves (`training_data` module name).
3. Fine-tune:
   ```powershell
   python finetune.py
   ```
4. Place/keep adapter at `./clr-finetuned`.
5. Agent will call `gemma_decider_local.py` for action labels; if unavailable, it falls back to built-in defaults.

## Quick tests

- `python test_load_score.py`: observe load-score behavior from live activity.
- `python test_vision.py`: camera + MediaPipe availability check.
- `python test_vision2.py`: hand/face geometry debug output.
- `python test_agent.py`: starts the agent loop directly.

## Notes and caveats

- This project is Windows-oriented (`pygetwindow`, global input hooks, desktop overlays).
- Window-title matching for distractions is keyword-based and may need tuning.
- Webcam and microphone access permissions are required for full functionality.
- Real-time loops run in daemon threads; production hardening (structured logging, graceful shutdown, stronger tests) is still open.

## License

MIT License (see `LICENSE`).
