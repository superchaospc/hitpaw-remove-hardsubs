# Finding every subtitle row

Measure subtitle position with this detector, over the full frame height, before choosing a
removal region. Do not measure from contact sheets: they are scaled down far enough that a
low-contrast cue disappears, and a cue that sits well away from the others is exactly the one
you will miss.

## Why edge transitions

Burned-in captions are light glyphs with a dark stroke, so each text row contains many abrupt
left-to-right luminance jumps. Ordinary scene content, even busy food, changes gradually along a
row. Counting large horizontal neighbour differences per row separates the two cleanly and costs
one greyscale decode pass.

## The scan

Decode greyscale frames at about 5 fps, and for each frame report every row band that crosses the
threshold. Print the bands per timestamp instead of a single overall range, so a cue that appears
for one second in an unusual place is visible in the output.

```python
import subprocess, numpy as np

W, H, FPS = width, height, 5          # W,H from ffprobe; never guess them
cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", path,
       "-vf", f"fps={FPS},format=gray", "-f", "rawvideo", "-"]
buf = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, dtype=np.uint8)

for i in range(len(buf) // (W * H)):
    f = buf[i*W*H:(i+1)*W*H].reshape(H, W).astype(np.int16)
    tr = (np.abs(np.diff(f, axis=1)) > 70).sum(axis=1)   # transitions per row
    ys = np.where(tr >= 25)[0]                            # text rows
    bands, start, prev = [], None, None
    for y in ys:                                          # group rows into bands
        if start is None: start = y
        elif y - prev > 12: bands.append((start, prev)); start = y
        prev = y
    if start is not None: bands.append((start, prev))
    print(round(i / FPS, 2), [b for b in bands if b[1] - b[0] >= 12])
```

Thresholds: a neighbour difference above 70 counts as an edge, 25 such edges make a text row,
rows more than 12 apart are separate bands, and a band under 12 rows tall is noise. These hold for
1080-wide vertical video with typical outlined captions. Widen them only with a reason, and say so.

## What it misses

The detector counts sharp edges, so it depends on the caption's dark outline. A plain white
caption with no stroke, sitting on a light plate or a steel pan, produces too few edges per row
and is reported as empty. Three such cues (芝麻盐, 撒芝士, 煎几个饺子) passed the strict scan
on a 2026-09-23 job. So:

- Before choosing the box, also run it at `FPS = 30` with the row threshold at 15. That pass is
  noisy (droplets, whiskers, bottle rims), so read it as "go look at these frames", not as bands.
- After HitPaw returns, the difference between the source (scaled to the result size) and the
  result shows where HitPaw removed something: rows with ≥10 pixels whose raw Y changed by >39
  (>45 on full-range grey). Use it **per caption, not per frame**. HitPaw also lightly repaints
  motion inside its box, so a whole-frame difference mask fires on caption-free frames. On
  2026-09-29 it covered all 2572 of 2572 frames. `scripts/composite-captions.py` measures each
  caption's rectangle only within that caption's frames and near its rows. Elsewhere, its stray
  report lists runs of repainted rows. A run marked `caption-like` (20+ frames on at most 120
  rows) is usually a caption, sticker or emoji that `CAPTIONS` is missing. On 2026-09-29 the
  only such run was a 🍔 sticker, which the edge scan never sees.

## From the loose scan to CAPTIONS

The composite needs one line per caption: `start end y0 y1 name`, source frame numbers
(inclusive) and source rows. `scripts/build-captions.py SOURCE CAPTIONS --sheet DIR` drafts it:

1. **Scan.** It runs the loose pass on every source frame. That is the 30 fps pass for 30 fps
   clips: edge >70, 15 edges per row, rows within 12 merge, bands under 12 rows dropped.
2. **Cluster.** A band that recurs on at least 8 frames becomes one candidate, provided its top
   and bottom rows each stay within 10 rows of where they started. Gaps of up to 2 frames are
   bridged. Captions are static and last about a second. Droplets and whiskers move or flicker,
   so they rarely hold one position for 8 frames.
3. **Refine.** Captions cut in and out hard. So the script counts edges inside each candidate's
   box on every frame from 24 before to 24 after it. The count steps between an off level (a few
   edges) and an on level (hundreds to thousands). Start and end move to where the count crosses
   halfway, up to 12 frames either way. This matters when something covers the caption for a
   while. On 2026-09-29 a pour of milk over 牛奶 cut the row count below 15, so the scan started
   11 frames late (2274). The box's edge count was already at its on level from 2263.
4. **Flag.** A candidate is written commented out as `#?` when its band is under 24 or over 120
   rows tall, its on/off contrast is under 8, or it has no clean cut within 12 frames. Real
   captions on 2026-09-29 showed contrasts of 17 to over 4000. The five texture bands showed 1.3
   to 2.4.

Frame counts are for 30 fps and rows for a 1920-row frame; the script scales both to the source.
The sheet has one strip per candidate, numbered like the names: the frame before the start, the
middle frame and the frame after the end, across the caption's rows. A good line shows text only
in the middle panel. Review every strip; the file is a draft, not a verdict. Lines it cannot
produce, you add by hand: unstroked white text and emoji stickers have too few edges to cluster.
`--save-scan` keeps the loose scan as JSON, and `--scan` reuses one.

On 2026-09-29 (86 s, 22 captions) the draft matched the hand-checked list frame for frame and
row for row, and flagged exactly the five non-caption bands.

The draft is built for **isolated** captions, each with clean frames before and after it, which
is the scattered-cue case that needs a tall box. It cannot split a fixed band where one caption
follows another back to back. There the off level beside each caption is its neighbour, so every
candidate is flagged and the refined cuts are meaningless. It also misses the second line of a
caption that wraps. A 720×1280 clip from 2026-10-07 drafted 17 candidates and flagged all 17.
For such a band, write `CAPTIONS` by hand: one line per stretch, with rows covering every text
line. The composite and the acceptance check handle that list normally.

## Turning the scan into a region

Take the union of every band the scan reported across the whole clip, then pad 20–30px on each
side. Padding is nearly free: pixels outside the removal region come from the source either way.
Missing one cue is not free, because the fix is a second paid job on the same clip.

## Verifying afterwards

Run the identical scan on the finished file, plus the 30 fps threshold-15 pass. An empty strict
result across every frame is necessary but not sufficient: the strict scan is blind to unstroked
captions, so view a source-vs-final crop of every stretch the loose pass flags. Inspecting a
handful of thumbnails is not a check. Report the
frame range and row band of anything that survives. `build-captions.py RESTORED OUT.txt --sheet
DIR` on the restored file is a quick way to cluster the loose pass: every unflagged line is a
band that survived.

Coverage is half of acceptance; the other half is that nothing outside the patches changed.
`scripts/check-outside-psnr.py SOURCE RESTORED` compares the composite with a control that is
the source re-encoded with the same x264 settings, measuring PSNR against the source outside
the patch rectangles on the raw Y, U and V planes. The two must agree within 0.5 dB.
On 2026-09-29 both scored Y 49.14 dB. The v1.2.0 rgb24 difference-mask composite scored 35.32 dB,
with mean Y −1.64. Do not measure through `format=gray`: it converts tagged
and untagged files differently and invents a shift of a couple of levels.
