#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 INPUT_VIDEO WORK_DIR" >&2
  exit 2
fi

input=$1
work_dir=$2
mkdir -p "$work_dir"

ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=index,codec_name,width,height,r_frame_rate \
  -of json "$input" > "$work_dir/probe.json"

duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$input")
sheet_count=$(awk -v d="$duration" 'BEGIN { n=int((d+47)/48); if (n<1) n=1; print n }')

for ((page=0; page<sheet_count; page++)); do
  start=$((page * 48))
  ffmpeg -y -v error -ss "$start" -i "$input" -t 48 \
    -vf "fps=1,scale=190:-1,tile=6x8:padding=4:margin=4:color=white" \
    -frames:v 1 "$work_dir/contact-$(printf '%02d' "$((page+1))").jpg"
done

printf 'Probe: %s\nContact sheets: %s/contact-*.jpg\n' "$work_dir/probe.json" "$work_dir"
