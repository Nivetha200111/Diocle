"""Trains one LoRA on Muse Glimmer 30B, then writes first translations of the held-out programs with the adapter on and off.

The same quantized weights serve both, so base and tuned differ only by the adapter. No scoring happens here: the answers are
checked against GnuCOBOL on the owner's machine (eval/distill_glimmer.py score). TUNE_SMOKE=1 runs every step on a tiny random
model on a CPU, so a mistake here costs nothing.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoConfig, AutoModelForImageTextToText, AutoTokenizer, BitsAndBytesConfig

BASE = "meta-models/Muse-Glimmer-30B"
SMOKE = os.environ.get("TUNE_SMOKE") == "1"
HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get("BT_CHECKPOINT_DIR", HERE / "out"))
EPOCHS, RANK, ALPHA, LR, SEED, EFFORT = 3, 8, 16, 2e-4, 7701, "low"
EVAL_SEED, K, MAX_NEW = 8801, 3, 16 if SMOKE else 8000
TARGETS = r".*language_model\.layers\.\d+\.(self_attn\.(q|k|v|o)_proj|mlp\.(up|down)_proj)"
STARTED = time.monotonic()
LIMIT = float(os.environ.get("TUNE_MINUTES", "100")) * 60
TRAIN_LIMIT = 55 * 60  # training that would take longer leaves no time for the answers, so it stops early and cheaply


def log(**fields) -> None:
    print(json.dumps({"minute": round((time.monotonic() - STARTED) / 60, 1), **fields}), flush=True)


def load(tok):
    if SMOKE:
        c = AutoConfig.from_pretrained(BASE)
        t = c.text_config
        t.hidden_size, t.intermediate_size, t.num_hidden_layers, t.num_attention_heads = 64, 128, 2, 2
        t.head_dim, t.layer_types, t.layer_rope_theta = 32, t.layer_types[:2], t.layer_rope_theta[:2]
        c.vision_config.num_hidden_layers = 1
        return AutoModelForImageTextToText.from_config(c, dtype=torch.float32)
    q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.bfloat16)
    return AutoModelForImageTextToText.from_pretrained(BASE, quantization_config=q, device_map={"": 0})


def render(tok, messages, *, prompt: bool) -> list[int]:
    return tok.apply_chat_template(messages, tokenize=True, return_dict=False, add_generation_prompt=prompt, reasoning_strength=EFFORT)


def inputs(ids, device) -> dict:
    x = torch.tensor([ids], device=device)
    return {"input_ids": x, "attention_mask": torch.ones_like(x)}


def train(model, tok, lines) -> None:
    device = next(model.parameters()).device
    examples = []
    for line in lines:
        ids, head = render(tok, line["messages"], prompt=False), render(tok, line["messages"][:-1], prompt=True)
        if ids[:len(head)] != head:
            raise SystemExit("the prompt is not a prefix of the training line")
        examples.append((ids, [-100] * len(head) + ids[len(head):]))
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model.config.use_cache = False
    model.train()
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=LR, weight_decay=0.0)
    rng = random.Random(SEED)
    started, done = time.monotonic(), 0
    for epoch in range(1, EPOCHS + 1):
        rng.shuffle(examples)
        total = 0.0
        for step, (ids, labels) in enumerate(examples, 1):
            loss = model(**inputs(ids, device), labels=torch.tensor([labels], device=device)).loss
            if not torch.isfinite(loss):
                raise SystemExit(f"loss is not finite at epoch {epoch} step {step}")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            total += loss.item()
            done += 1
            projected = (time.monotonic() - started) / done * EPOCHS * len(examples)
            if done >= 5 and projected > TRAIN_LIMIT:
                raise SystemExit(f"too slow: training would take {projected / 60:.0f} minutes")
            if step == 1 or step % 5 == 0:
                log(stage="train", epoch=epoch, step=step, loss=round(loss.item(), 4))
        model.save_pretrained(OUT / "adapter")
        log(stage="epoch", epoch=epoch, meanLoss=round(total / len(examples), 4), adapterSaved=True)


def generate(model, tok, program: dict, which: str, device) -> None:
    ids = render(tok, program["messages"], prompt=True)
    torch.manual_seed(EVAL_SEED)  # the same seed for base and tuned
    started = time.monotonic()
    kwargs = inputs(ids, device)
    with torch.inference_mode():
        out = model.generate(**kwargs, max_new_tokens=MAX_NEW, do_sample=True, num_return_sequences=K, use_cache=True)
    seconds = round(time.monotonic() - started, 1)
    for trial, row in enumerate(out, 1):
        answer = row[len(ids):].tolist()
        text = tok.decode(answer, skip_special_tokens=False)
        path = OUT / "generations" / f"{program['name']}-{which}-{trial}.json"
        path.write_text(json.dumps({"program": program["name"], "which": which, "trial": trial, "text": text,
                                    "outputTokens": sum(t != tok.pad_token_id for t in answer), "seconds": seconds}))
    log(stage="generated", program=program["name"], which=which, seconds=seconds)


def main() -> int:
    log(stage="start", torch=torch.__version__, gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)
    (OUT / "generations").mkdir(parents=True, exist_ok=True)
    lines = [json.loads(x) for x in (HERE / "train.jsonl").read_text().splitlines()]
    programs = [json.loads(x) for x in (HERE / "held-out.jsonl").read_text().splitlines()]
    if SMOKE:
        lines, programs = lines[:2], programs[:1]
    tok = AutoTokenizer.from_pretrained(BASE)
    model = load(tok)
    log(stage="loaded", memoryGb=round(torch.cuda.memory_allocated() / 1e9, 1) if torch.cuda.is_available() else 0)
    if not SMOKE:
        from peft import prepare_model_for_kbit_training
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=False)
    model = get_peft_model(model, LoraConfig(r=RANK, lora_alpha=ALPHA, target_modules=TARGETS, lora_dropout=0.0, bias="none"))
    log(stage="lora", trainable=sum(p.numel() for p in model.parameters() if p.requires_grad))
    train(model, tok, lines)
    model.gradient_checkpointing_disable()
    model.config.use_cache = True
    model.eval()
    device = next(model.parameters()).device
    assert isinstance(model, PeftModel)
    for program in programs:
        for which in ("base", "tuned"):
            if time.monotonic() - STARTED > LIMIT:
                log(stage="out-of-time", program=program["name"], which=which)  # exits 0: the host uploads files fully only then
                return 0
            if which == "base":
                with model.disable_adapter():
                    generate(model, tok, program, which, device)
            else:
                generate(model, tok, program, which, device)
    log(stage="done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
