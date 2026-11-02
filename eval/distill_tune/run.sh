#!/bin/bash
# Everything, install included, runs under one limit. At $0.10833 a minute, 110 minutes is $11.92. Exit 0 when time runs out:
# the host finishes uploading checkpoints only for a completed job, and answers already written still count.
set -ux
export HF_HOME="$BT_PROJECT_CACHE_DIR/hf" TUNE_MINUTES=100
timeout 6600 bash -c 'set -e
pip install --no-cache-dir transformers==5.22.1 peft==0.21.2 accelerate==1.15.0 bitsandbytes==0.50.2 jinja2==3.1.6
python tune.py'
code=$?
if [ "$code" = 124 ]; then exit 0; fi
exit "$code"
