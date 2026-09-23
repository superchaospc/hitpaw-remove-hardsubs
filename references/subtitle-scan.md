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
- After HitPaw returns, the reliable locator is the difference between the source (scaled to the
  result size) and the result: rows with ≥10 pixels changed by >45 are rows HitPaw repainted.
  `scripts/composite-mask.py` unions that with this scan to build its mask.

## Turning the scan into a region

Take the union of every band the scan reported across the whole clip, then pad 20–30px on each
side. Padding is nearly free: pixels outside the removal region come from the source either way.
Missing one cue is not free, because the fix is a second paid job on the same clip.

## Verifying afterwards

Run the identical scan on the finished file, plus the 30 fps threshold-15 pass. An empty strict
result across every frame is necessary but not sufficient: the strict scan is blind to unstroked
captions, so view a source-vs-final crop of every stretch the loose pass flags. Inspecting a
handful of thumbnails is not a check. Report the
frame range and row band of anything that survives.
