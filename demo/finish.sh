#!/bin/sh
# Finish the promo with the narration: captions from the voice (whisper.cpp, offline), then video + voice + captions.
#   demo/finish.sh path/to/voiceover.m4a
# Reads demo/promo/out/promo.mp4 (npm run render in demo/promo) and writes demo/promo/out/final.mp4 and captions.srt.
# The video is cut or held to the narration's length; retime scenes in demo/promo/src/Promo.tsx (SCENES) to match.
set -eu
voice=$1
out="$(dirname "$0")/promo/out"
model=${WHISPER_MODEL:-$HOME/.cache/whisper/ggml-base.en.bin}
ffmpeg -v error -y -i "$voice" -ar 16000 -ac 1 "$out/voice16k.wav"
whisper-cli -m "$model" -f "$out/voice16k.wav" -osrt -of "$out/captions" >/dev/null 2>&1
echo "captions: $out/captions.srt (check the spelling of Diocle, Muse Spark, GnuCOBOL before publishing)"
ffmpeg -v error -y -i "$out/promo.mp4" -i "$voice" \
  -vf "subtitles=$out/captions.srt:force_style='FontName=IBM Plex Sans,FontSize=18,Outline=2,MarginV=40'" \
  -af "loudnorm=I=-16:TP=-1.5:LRA=11" -map 0:v -map 1:a -c:v libx264 -preset slow -crf 17 -c:a aac -b:a 192k \
  -shortest "$out/final.mp4"
echo "final: $out/final.mp4 ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out/final.mp4")s)"
