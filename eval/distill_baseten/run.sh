#!/bin/bash
# TUNE_MINUTES is the budget inside tune.py; the timeout below is the backstop. At $0.10833 a minute, 110 minutes is $11.92.
set -eux
pip install --no-cache-dir "transformers==5.22.1" "peft>=0.17" "accelerate>=1.0" "bitsandbytes>=0.46" "jinja2>=3.1"
export HF_HOME="$BT_PROJECT_CACHE_DIR/hf" TUNE_MINUTES=100
timeout 6600 python tune.py
