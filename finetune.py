# finetune.py
import os
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer
from datasets import Dataset
from training_data import format_examples

MODEL_ID = "google/functiongemma-270m-it"
OUTPUT_DIR = "./clr-finetuned"

token = os.environ.get("HF_TOKEN")

print("Loading base model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=token)
model = AutoModelForCausalLM.from_pretrained(MODEL_ID, token=token, device_map="auto")

lora_config = LoraConfig(
    r=8,
    lora_alpha=16,
    target_modules=["q_proj", "v_proj"],
    lora_dropout=0.05,
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, lora_config)

examples = format_examples()

def to_text(ex):
    state = ex["prompt"]
    action = ex["action"]
    prompt = f"Signal state: {state}. Decide the best action:"
    completion = f" {action}"
    return {"text": prompt + completion}

dataset = Dataset.from_list(examples).map(to_text)

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    num_train_epochs=5,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=1,
    learning_rate=2e-4,
    fp16=True,
    logging_steps=10,
    save_steps=100,
    report_to="none",
)

def formatting_func(batch):
    return batch["text"]

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    formatting_func=formatting_func,
)

print("Starting fine-tuning...")
trainer.train()
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print("Done. Saved to", OUTPUT_DIR)
