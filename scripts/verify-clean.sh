#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 OUTPUT_VIDEO VERIFY_DIR" >&2
  exit 2
fi

video=$1
verify_dir=$2
mkdir -p "$verify_dir"

ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=index,codec_name,width,height \
  -of json "$video" > "$verify_dir/probe.json"

duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$video")
sheet_count=$(awk -v d="$duration" 'BEGIN { n=int((d+47)/48); if (n<1) n=1; print n }')
for ((page=0; page<sheet_count; page++)); do
  start=$((page * 48))
  ffmpeg -y -v error -ss "$start" -i "$video" -t 48 \
    -vf "fps=1,scale=190:-1,tile=6x8:padding=4:margin=4:color=white" \
    -frames:v 1 "$verify_dir/verify-$(printf '%02d' "$((page+1))").jpg"
done

ffmpeg -v error -i "$video" -f null -
printf 'Decode passed. Visually inspect: %s/verify-*.jpg\n' "$verify_dir"
