# gemma_decider_local.py
import os, json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE_ID     = "google/functiongemma-270m-it"
ADAPTER_DIR = "./clr-finetuned"

ALLOWED = {
    "hide_chat_and_focus_work",
    "rage_break",
    "soft_nudge",
    "enforce_break",
    "no_action",
}

token = os.environ.get("HF_TOKEN")
if not token:
    raise RuntimeError('HF_TOKEN not set. Run: $env:HF_TOKEN="hf_..."')

print("[Gemma] Loading base model…")
_base  = AutoModelForCausalLM.from_pretrained(BASE_ID, token=token, device_map="auto")
print("[Gemma] Loading LoRA adapter…")
_model = PeftModel.from_pretrained(_base, ADAPTER_DIR)
_tok   = AutoTokenizer.from_pretrained(ADAPTER_DIR)
if _tok.pad_token is None:
    _tok.pad_token = _tok.eos_token
_model.eval()
print("[Gemma] Ready ✓")


def _sanitize(raw: str) -> str:
    if not raw:
        return "no_action"
    # strip parens (old training used no_action())
    a = raw.strip().splitlines()[0].strip().strip(' "\'`.,').replace("()", "")
    if a in ALLOWED:
        return a
    lo = a.lower()
    if "hide"   in lo: return "hide_chat_and_focus_work"
    if "rage"   in lo: return "rage_break"
    if "nudge"  in lo: return "soft_nudge"
    if "break"  in lo: return "enforce_break"
    return "no_action"


def get_label(state: dict) -> str:
    # Prompt matches the training_data format_examples() template
    state_str = json.dumps(state)
    prompt = (
        f"Signal state: {state_str}\n"
        f"Choose exactly one action from: "
        f"['hide_chat_and_focus_work','rage_break','soft_nudge','enforce_break','no_action']\n"
        f"Action:"
    )
    inputs = _tok(prompt, return_tensors="pt")
    inputs = {k: v.to(_model.device) for k, v in inputs.items()}

    with torch.no_grad():
        out = _model.generate(
            **inputs,
            max_new_tokens=12,
            do_sample=False,
            pad_token_id=_tok.eos_token_id,
        )

    decoded = _tok.decode(out[0], skip_special_tokens=True)
    raw     = decoded.split("Action:")[-1].strip()
    result  = _sanitize(raw)
    print(f"[Gemma] raw='{raw}' → '{result}'")
    return result