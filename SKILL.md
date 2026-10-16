---
name: hitpaw-remove-hardsubs
description: Remove burned-in or hardcoded subtitles from MP4/MOV cooking and short-form videos with HitPaw Edimakor on macOS. Use when asked to 自动去字幕、删除全部字幕、去除不同位置或移动字幕、批量检查字幕区域、从卡在 Downloading 的 HitPaw 任务取回结果，或验证无字幕视频成品。
---

# HitPaw Remove Hardsubs

Remove hard subtitles with an inspect → choose scope → process → retrieve → verify workflow. Keep source files unchanged and place finished files in `~/Movies/去字幕成品/` unless the user specifies otherwise. Every finished file is vertical 1080×1920.

## Workflow

1. Run `scripts/inspect-video.sh INPUT WORK_DIR` to probe the video and create full-frame contact sheets.
2. Locate the subtitles by scanning the **entire frame height**, never by eye and never within a
   guessed band. Contact sheets are for judging damage risk, not for measuring position: shrunk to
   thumbnail size, a low-contrast cue is invisible. Run the detector in
   [references/subtitle-scan.md](references/subtitle-scan.md) over every row from 0 to the full
   height, list the row ranges it reports per frame, and take the union of all of them.
   The edge scan only sees **outlined** captions. Plain white captions without a dark stroke
   (small cooking-step labels like 芝麻盐) score almost no edges and come back empty. Also run
   the scan at 30 fps with the row threshold lowered to 15, and look at every frame it flags.
   Treat the union as a floor, not the whole truth: pad the box generously.
3. Choose the region from that union:
   - Use a tight band when the union stays within one stripe; pad it 20–30px top and bottom.
   - When small cues are scattered over a tall stretch (for example y≈500–1650 on a 1920 frame),
     one tall full-width box in **Remove text** mode is one job. Remove text repaints only the text
     it detects, and it leaves packaging and label text alone. The composite in step 10 then keeps
     source pixels everywhere except a rectangle around each caption, so a tall box costs no
     resolution.
   - Use the full visible video frame when the cues are scattered too far to band together.
   - Warn that full-frame removal may erase meaningful text on packaging, signs, interfaces, or utensils.
   - A band that is too wide costs nothing, because pixels outside it still come from the source.
     A band that misses one cue costs a whole second job.
4. Copy or link an awkward Unicode filename to an ASCII working filename when the macOS file picker is unreliable. Never alter the source.
5. Drive HitPaw Edimakor in **background app mode** (`app_screenshot` / `app_click` / `app_drag`), so the user keeps their mouse and their frontmost app while you work. Full-screen control is permitted only for the file-open dialog, and only as keyboard actions — see [references/hitpaw-gui.md](references/hitpaw-gui.md). Prefer accessibility elements; use coordinates only after reading the current screenshot. Re-measure the preview rectangle whenever the window changes.
6. Read the AI-credit balance in the header **before** you commit to a plan, and confirm the job fits inside it. The Remove button shows the task price next to the balance; if the balance is short, say so and stop rather than discovering it at the click. Never buy credits.
7. Choose the removal mode: the panel offers Remove watermark, **Remove text**, Remove mosaic and Quick blur (there is no "Remove subtitles"). Use Remove text for captions. Set the selected region, submit once, and accept the 1080P compatibility conversion. That Confirm button sits in a separate dialog window that refuses background clicks, so give it one foreground click. Do not resubmit a slow task because that can consume credits again.
8. Poll the newest HitPaw log for a new result URL with `scripts/fetch-result.sh --wait OUTPUT`. The script switches the known US OSS host to its acceleration endpoint automatically.
9. Inspect the downloaded result at one frame per second across its entire duration. If a final nutrition card or other text panel remains, trim at the first frame where it appears rather than trying to reconstruct the covered image.
10. Restore the source resolution first. HitPaw caps the long edge at 1080, so a 720×1280 or 1080×1920 source comes back as 608×1080. For a band or tall-box region, paste HitPaw pixels back inside **one feathered rectangle per confirmed caption** and keep the source everywhere else. Run the scripts with a Python that has numpy; the newest system/Homebrew Python often lacks it.
    - **Captions list.** `scripts/build-captions.py SOURCE CAPTIONS --sheet WORK_DIR/sheets` drafts `CAPTIONS`, one line per caption: `start end y0 y1 name`, in source frame numbers (inclusive) and source rows. It runs the loose 30 fps scan, clusters bands that persist for at least 8 frames with row drift under 10, and refines each start and end from per-frame edge counts in that caption's rows. View every sheet. Each strip must show its caption only in the middle panel, with the frame before and the frame after clean. Lines marked `#?` are suspects (wrong height, weak on/off contrast, no hard cut); keep one only after looking at it. The edge scan cannot see unstroked white text or emoji stickers, so add those lines by hand. The draft is for isolated captions. For a fixed band where captions follow each other back to back, or wrap onto two lines, it flags everything: write those lines by hand, one per stretch, with rows covering every text line. Details: [references/subtitle-scan.md](references/subtitle-scan.md).
    - **Composite.** `scripts/composite-captions.py SOURCE HITPAW CAPTIONS RESTORED --box X0 X1 Y0 Y1` (`--box` = the HitPaw selection in source pixels) measures the frame offset. Each caption's rectangle is where HitPaw changed pixels near its rows during its frames, padded and feathered. The script blends the Y, U and V planes directly, tags the raw input with the source's colour description, copies the source audio and writes `RESTORED.rects.json`.
    - **Its stray report.** Read the "repainted outside every caption" runs, and look first at any marked `caption-like`. That mark means the run lasted 20+ frames at 30 fps on at most 120 of 1920 rows. Such a run is usually a caption, sticker or emoji missing from `CAPTIONS`: add the line and rerun. On 2026-09-29 the report listed 14 runs. One was real, a 🍔 sticker at frames 2061–2087. The rest were short or spread over hundreds of rows: droplets, sesame seeds, a strainer's mesh.
    - **Acceptance.** Run `scripts/check-outside-psnr.py SOURCE RESTORED`. It makes a control, `RESTORED.control.mp4`: the source re-encoded with the same x264 settings and nothing else changed. Then it compares Y, U and V PSNR against the source **outside the patch rectangles**. Outside them the composite must match the control within 0.5 dB on every plane. On 2026-09-29 both scored Y 49.14, U 53.22 and V 54.22 dB. The v1.2.0 composite scored Y 35.32 dB there, with mean Y shifted by −1.64. Several dB lower means the pipeline is changing pixels it should not touch, so fix it before you deliver.
    - Do not go back to a whole-frame difference mask (the v1.2.0 `composite-mask.py`). HitPaw lightly repaints motion inside the box, so on 2026-09-29 that mask covered all 2572 frames and pasted 608-px pixels everywhere. Do not pipe rgb24, and do not tag colour only on the output side either. Both range-convert every untouched pixel: 43 dB outside the patch, Y shifted about −1.7 across the whole frame.
    - Never mux with `-shortest`: the source audio is often a few ms shorter, and `-shortest` silently drops the last frames. For a full-frame region, upscale the whole HitPaw result to the source size with Lanczos, and tell the user those pixels are reconstructed. Preserve the source audio.
11. Conform every finished file to vertical **1080×1920**, whatever the source size: `scripts/conform-vertical.sh RESTORED FINAL`. It fit-scales the picture, centres it on black when the aspect is not 9:16, never crops or stretches, copies audio, keeps every frame, and stream-copies media that is already 1080×1920. Deliver only `FINAL`. It refuses to overwrite an existing `FINAL`, so on a rerun delete the old one first; otherwise you verify a stale file. Do not skip step 10 and conform the 608×1080 result directly: that throws away source detail the composite keeps.
12. Run `scripts/verify-clean.sh FINAL VERIFY_DIR`. It fails unless the file is exactly 1080×1920 with square pixels. View every generated sheet, run the subtitle scan on `FINAL` (both the strict 5 fps pass and the 30 fps threshold-15 pass), and view a source-vs-final crop of every stretch the loose pass flags. Water droplets and shrimp whiskers trip it too, so judge by eye. The step 10 outside-patch PSNR check must have passed. Confirm the complete decode before claiming completion.

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
