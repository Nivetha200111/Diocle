#!/bin/sh
# Assemble the demo video from the recorded shots (record.mjs) with ffmpeg.
#   demo/build.sh                         # out/rough-cut.mp4: all shots in order, 1920x1080, silent
#   demo/build.sh voiceover.m4a [subs.srt] # out/final.mp4: rough cut + your narration (+ burned-in captions)
# Shot order follows docs/DEMO_PLAN.md. A shot can be trimmed or slowed by editing SHOTS below:
# name[:start-end seconds][:speed], e.g. "import:0-12:1" or "delivery::0.8" (0.8 = slower).
set -eu
cd "$(dirname "$0")/out"
SHOTS="title home chqclr delivery reverify import evaluation closing"

parts=""
for spec in $SHOTS; do
  name=${spec%%:*}
  rest=${spec#"$name"}; rest=${rest#:}
  range=${rest%%:*}; speed=${rest#"$range"}; speed=${speed#:}; speed=${speed:-1}
  trim=""
  if [ -n "$range" ]; then trim="-ss ${range%-*} -to ${range#*-}"; fi
  # 1280x720 recording whose page fills the top 1280x640 (Chrome screencast) -> 1920x1080, 30 fps, H.264;
  # setpts changes speed (label speed-ups in the edit).
  ffmpeg -v error -y $trim -i "$name.webm" \
    -vf "crop=1280:640:0:0,scale=1920:1080:flags=lanczos,fps=30,setpts=PTS/$speed,format=yuv420p" \
    -an -c:v libx264 -preset medium -crf 18 "part-$name.mp4"
  parts="$parts part-$name.mp4"
done
: > parts.txt
for p in $parts; do echo "file '$p'" >> parts.txt; done
ffmpeg -v error -y -f concat -safe 0 -i parts.txt -c copy rough-cut.mp4
echo "rough cut: $(pwd)/rough-cut.mp4 ($(ffprobe -v error -show_entries format=duration -of csv=p=0 rough-cut.mp4)s)"

if [ $# -ge 1 ]; then
  voice=$1
  subs=${2:-}
  vf="null"
  if [ -n "$subs" ]; then vf="subtitles=$subs:force_style='FontName=Helvetica,FontSize=20,Outline=2'"; fi
  # Video length follows the narration; loudness normalised for YouTube.
  ffmpeg -v error -y -i rough-cut.mp4 -i "$voice" -vf "$vf" -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
    -map 0:v -map 1:a -c:v libx264 -preset medium -crf 18 -c:a aac -b:a 192k -shortest final.mp4
  echo "final: $(pwd)/final.mp4 ($(ffprobe -v error -show_entries format=duration -of csv=p=0 final.mp4)s)"
fi
