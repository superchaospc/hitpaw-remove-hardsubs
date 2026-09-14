#!/usr/bin/env bash
set -euo pipefail

# Every finished file must be vertical 1080x1920; run scripts/conform-vertical.sh first.
DELIVERY_SIZE=1080x1920

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 OUTPUT_VIDEO VERIFY_DIR" >&2
  exit 2
fi

video=$1
verify_dir=$2
mkdir -p "$verify_dir"

ffprobe -v error \
  -show_entries format=duration,size \
  -show_entries stream=index,codec_name,width,height,sample_aspect_ratio \
  -of json "$video" > "$verify_dir/probe.json"

size=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$video")
sar=$(ffprobe -v error -select_streams v:0 -show_entries stream=sample_aspect_ratio -of csv=p=0 "$video")
if [[ $size != "$DELIVERY_SIZE" || ( $sar != 1:1 && $sar != N/A && $sar != 0:1 ) ]]; then
  printf 'Size check failed: %s (SAR %s), expected %s. Run scripts/conform-vertical.sh first.\n' "$size" "$sar" "$DELIVERY_SIZE" >&2
  exit 1
fi

duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$video")
sheet_count=$(awk -v d="$duration" 'BEGIN { n=int((d+47)/48); if (n<1) n=1; print n }')
for ((page=0; page<sheet_count; page++)); do
  start=$((page * 48))
  ffmpeg -y -v error -ss "$start" -i "$video" -t 48 \
    -vf "fps=1,scale=190:-1,tile=6x8:padding=4:margin=4:color=white" \
    -frames:v 1 "$verify_dir/verify-$(printf '%02d' "$((page+1))").jpg"
done

ffmpeg -v error -i "$video" -f null -
printf 'Size %s and decode passed. Visually inspect: %s/verify-*.jpg\n' "$size" "$verify_dir"
