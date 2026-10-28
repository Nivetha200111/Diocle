#!/bin/sh
# Finish the promo with the narration: captions from the voice (whisper.cpp, offline), then video + voice + captions.
#   demo/finish.sh path/to/voiceover.m4a [video]
# Reads the video (default demo/promo/out/diocle-submission.mp4, the merged cut) and writes
# demo/promo/out/final.mp4 and captions.srt.
# The video keeps its length; record the narration to the timings in docs/DEMO_PLAN.md (merged cut).
set -eu
voice=$1
out="$(dirname "$0")/promo/out"
model=${WHISPER_MODEL:-$HOME/.cache/whisper/ggml-base.en.bin}
ffmpeg -v error -y -i "$voice" -ar 16000 -ac 1 "$out/voice16k.wav"
whisper-cli -m "$model" -f "$out/voice16k.wav" -osrt -of "$out/captions" >/dev/null 2>&1
echo "captions: $out/captions.srt (check the spelling of Diocle, Muse Spark, GnuCOBOL before publishing)"
video=${2:-$out/diocle-submission.mp4}
# The video's own sound (clicks, whooshes, chimes) stays under the voice; the result is loudness-normalised.
ffmpeg -v error -y -i "$video" -i "$voice" \
  -filter_complex "[0:a]volume=0.55[fx];[1:a]volume=1.0[vo];[fx][vo]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11[a];[0:v]subtitles=$out/captions.srt:force_style='FontName=IBM Plex Sans,FontSize=18,Outline=2,MarginV=40'[v]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 17 -c:a aac -b:a 192k "$out/final.mp4"
echo "final: $out/final.mp4 ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out/final.mp4")s)"
