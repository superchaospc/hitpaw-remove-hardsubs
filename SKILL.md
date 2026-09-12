---
name: hitpaw-remove-hardsubs
description: Remove burned-in or hardcoded subtitles from MP4/MOV cooking and short-form videos with HitPaw Edimakor on macOS. Use when asked to 自动去字幕、删除全部字幕、去除不同位置或移动字幕、批量检查字幕区域、从卡在 Downloading 的 HitPaw 任务取回结果，或验证无字幕视频成品。
---

# HitPaw Remove Hardsubs

Remove hard subtitles with an inspect → choose scope → process → retrieve → verify workflow. Keep source files unchanged and place finished files in `~/Movies/去字幕成品/` unless the user specifies otherwise.

## Workflow

1. Run `scripts/inspect-video.sh INPUT WORK_DIR` to probe the video and create full-frame contact sheets.
2. Locate the subtitles by scanning the **entire frame height**, never by eye and never within a
   guessed band. Contact sheets are for judging damage risk, not for measuring position: shrunk to
   thumbnail size, a low-contrast cue is invisible. Run the detector in
   [references/subtitle-scan.md](references/subtitle-scan.md) over every row from 0 to the full
   height, list the row ranges it reports per frame, and take the union of all of them.
3. Choose the region from that union:
   - Use a tight band when the union stays within one stripe; pad it 20–30px top and bottom.
   - Use the full visible video frame when the cues are scattered too far to band together.
   - Warn that full-frame removal may erase meaningful text on packaging, signs, interfaces, or utensils.
   - A band that is too wide costs nothing, because pixels outside it still come from the source.
     A band that misses one cue costs a whole second job.
4. Copy or link an awkward Unicode filename to an ASCII working filename when the macOS file picker is unreliable. Never alter the source.
5. Drive HitPaw Edimakor in **background app mode** (`app_screenshot` / `app_click` / `app_drag`), so the user keeps their mouse and their frontmost app while you work. Full-screen control is permitted only for the file-open dialog, and only as keyboard actions — see [references/hitpaw-gui.md](references/hitpaw-gui.md). Prefer accessibility elements; use coordinates only after reading the current screenshot. Re-measure the preview rectangle whenever the window changes.
6. Read the AI-credit balance in the header **before** you commit to a plan, and confirm the job fits inside it. The Remove button shows the task price next to the balance; if the balance is short, say so and stop rather than discovering it at the click. Never buy credits.
7. Choose **Remove subtitles**, set the selected region, submit once, and accept the 1080P compatibility conversion when required. Do not resubmit a slow task because that can consume credits again.
8. Poll the newest HitPaw log for a new result URL with `scripts/fetch-result.sh --wait OUTPUT`. The script switches the known US OSS host to its acceleration endpoint automatically.
9. Inspect the downloaded result at one frame per second across its entire duration. If a final nutrition card or other text panel remains, trim at the first frame where it appears rather than trying to reconstruct the covered image.
10. Restore vertical output to 1080×1920 when HitPaw returns 608×1080. Use Lanczos scaling and mild sharpening; preserve audio.
11. Run `scripts/verify-clean.sh OUTPUT VERIFY_DIR`. View every generated sheet, then run a complete decode check before claiming completion.

## Safety and privacy

- Never store API keys, signed URLs, task UUIDs, account balances, user names, source videos, screenshots, logs, or absolute home paths in this skill.
- Resolve the home directory at runtime. Keep temporary URLs only in process output.
- Preserve original media. Write intermediates under a caller-provided work directory.
- Treat cloud submission as consuming paid credits. Confirm the exact file and region before clicking Remove, then submit only once.
- If removal visibly damages food, hands, tools, or other important content, report it and keep the raw processed result for comparison.

## GUI details

Read [references/hitpaw-gui.md](references/hitpaw-gui.md) before controlling HitPaw or troubleshooting a stalled download.

## Example requests

- “自动去掉这个视频的全部字幕。”
- “字幕在多个地方出现，帮我全画面去字并验收。”
- “HitPaw 已处理完成但一直卡在 Downloading，帮我取回。”
- “把 Downloads 里的三条视频逐个检查并去字幕。”
