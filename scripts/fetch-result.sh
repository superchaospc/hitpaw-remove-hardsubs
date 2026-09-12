#!/usr/bin/env bash
set -euo pipefail

wait_mode=0
if [[ ${1:-} == "--wait" ]]; then
  wait_mode=1
  shift
fi
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 [--wait] OUTPUT_MP4" >&2
  exit 2
fi

output=$1
log_dir="${HITPAW_LOG_DIR:-$HOME/Library/Caches/HitPaw Edimakor/HitpawEdimakor}"
deadline=$((SECONDS + ${HITPAW_WAIT_SECONDS:-1800}))
existing=''

latest_url() {
  local latest
  latest=$(find "$log_dir" -type f -name '*.log' -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -1 || true)
  [[ -n $latest ]] || return 1
  # Edimakor writes the finished URL under either marker. A job that the app itself failed to
  # download logs only "FileReady url:", so matching the other marker alone loses the result.
  sed -n -E 's/.*(removeWatermark result url|FileReady url): "([^"]*)".*/\2/p' "$latest" | tail -1
}

existing=$(latest_url || true)
while :; do
  url=$(latest_url || true)
  if [[ -n $url && ($wait_mode -eq 0 || $url != "$existing") ]]; then
    break
  fi
  if [[ $wait_mode -eq 0 || $SECONDS -ge $deadline ]]; then
    echo "No new HitPaw result URL found." >&2
    exit 1
  fi
  sleep 5
done

accelerated=${url/edimakorpc-us-prod.oss-us-east-1.aliyuncs.com/edimakorpc-us-prod.oss-accelerate.aliyuncs.com}
mkdir -p "$(dirname "$output")"
part="${output}.part"
if ! curl --fail --location --retry 8 --retry-all-errors --retry-delay 2 --connect-timeout 20 "$accelerated" -o "$part"; then
  curl --fail --location --retry 3 --retry-all-errors --retry-delay 2 --connect-timeout 20 "$url" -o "$part"
fi
mv "$part" "$output"
ffprobe -v error -show_entries format=duration,size -show_entries stream=index,codec_name,width,height -of json "$output"
