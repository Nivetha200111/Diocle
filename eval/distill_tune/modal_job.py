"""Modal route for the one tuning job in docs/DISTILLATION.md: one H100, stopped by Modal itself at 110 minutes.

  MODAL_TOKEN_ID=... MODAL_TOKEN_SECRET=... modal run --detach eval/distill_tune/modal_job.py
  modal volume get diocle-distill generations eval/distill_tune/out/

Same code as the Baseten route: tune.py trains and writes answers, and nothing is scored here. The volume keeps the adapter and
the answers, saved every minute, so answers written before the time limit survive it. No Modal retries: the plan allows one job.
"""
import os
import subprocess
import threading
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
image = (modal.Image.debian_slim(python_version="3.11")
         .pip_install("torch==2.7.0", "transformers==5.22.1", "peft==0.21.2", "accelerate==1.15.0", "bitsandbytes==0.50.2", "jinja2==3.1.6")
         .add_local_file(HERE / "tune.py", "/job/tune.py")
         .add_local_file(HERE / "train.jsonl", "/job/train.jsonl")
         .add_local_file(HERE / "held-out.jsonl", "/job/held-out.jsonl"))
app = modal.App("diocle-distill")
volume = modal.Volume.from_name("diocle-distill", create_if_missing=True)


@app.function(image=image, gpu="H100", cpu=4, memory=90 * 1024, timeout=6600, retries=0, volumes={"/out": volume})
def tune() -> int:
    stop = threading.Event()

    def keep() -> None:
        while not stop.wait(60):
            volume.commit()

    threading.Thread(target=keep, daemon=True).start()
    env = {**os.environ, "BT_CHECKPOINT_DIR": "/out", "HF_HOME": "/tmp/hf", "TUNE_MINUTES": "100"}
    code = subprocess.run(["python", "/job/tune.py"], env=env, cwd="/job").returncode
    stop.set()
    volume.commit()
    print(f"tune.py exit {code}", flush=True)
    return code


@app.local_entrypoint()
def main() -> None:
    tune.remote()
