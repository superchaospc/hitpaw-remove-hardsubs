#!/usr/bin/env python3
"""Draft the CAPTIONS file for composite-captions.py from the loose edge scan.

Usage:
  build-captions.py SOURCE CAPTIONS [--sheet DIR] [--scan SCAN.json | --save-scan SCAN.json]

SOURCE     the original video (frame numbers and rows in CAPTIONS refer to it)
CAPTIONS   output: one line per caption, START END Y0 Y1 NAME, with a comment after each line
--sheet    write review sheets DIR/captions-NN.jpg: one strip per candidate, numbered like the
           names, showing [frame before START | middle frame | frame after END] across its rows
--scan     reuse a loose-scan JSON ([[seconds, [[y0, y1, x0, x1], ...]], ...] per source frame)
--save-scan  save this run's loose scan in that format

1. Scan every source frame with the loose pass of references/subtitle-scan.md: |dx| > 70 is an
   edge, 15 edges make a text row, rows closer than 12 merge, bands under 12 rows are dropped.
2. Cluster: a band that recurs on at least 8 frames, its top and bottom rows each drifting under
   10 rows from where it started, is one candidate. Gaps of up to 2 frames are bridged.
3. Refine: count edges inside each candidate's box on every frame from 24 before to 24 after
   it. Captions cut in and out hard, so the count steps between an off level and an on level.
   START and END move to where the count crosses halfway, up to 12 frames either way. This
   recovers starts the scan missed while something covered the caption, such as a pour of milk.
4. Flag: a band under 24 or over 120 rows tall, an on/off contrast under 8, or no clean cut
   within 12 frames, is written commented out as '#?'. Review every line against the sheets.
Frame counts are for 30 fps and rows for a 1920-row frame; both scale with the source.
Needs numpy and ffmpeg/ffprobe.
"""
import argparse, json, os, subprocess, sys
import numpy as np

EDGE, ROW, BAND_GAP, BAND_MIN = 70, 15, 12, 12   # loose pass of subtitle-scan.md
MIN_FRAMES, GAP, WIN = 8, 2, 12                  # frames at 30 fps
DRIFT, MIN_H, MAX_H = 10, 24, 120                # rows on a 1920-row frame
MIN_CONTRAST, BOX_PAD_Y, BOX_PAD_X = 8, 4, 10
SHEET_ROWS, PER_SHEET = 24, 10
DIGITS = ["111101101101111", "010110010010111", "111001111100111", "111001111001111",
          "101101111001001", "111100111001111", "111100111101111", "111001001001001",
          "111101111101111", "111101111001111"]  # 3x5 bitmaps for sheet labels


def gray(path, w, h):
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-map", "0:v:0",
                          "-vf", "format=gray", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    try:
        while True:
            b = p.stdout.read(w * h)
            if len(b) < w * h:
                return
            yield np.frombuffer(b, np.uint8).reshape(h, w).astype(np.int16)
    finally:
        p.kill(); p.wait()


def edges(f):
    return np.abs(np.diff(f, axis=1)) > EDGE


def scan_bands(f):
    e = edges(f)
    ys = np.where(e.sum(axis=1) >= ROW)[0]
    out, start, prev = [], None, None
    for y in list(ys) + [10**9]:
        if start is not None and y - prev > BAND_GAP:
            if prev - start >= BAND_MIN:
                cols = np.where(e[start:prev + 1].sum(axis=0) >= 2)[0]
                out.append([int(start), int(prev), int(cols.min()) if len(cols) else -1,
                            int(cols.max()) if len(cols) else -1])
            start = None
        if start is None:
            start = y
        prev = y
    return out


def cluster(scan, min_frames, gap, drift):
    done, live = [], []
    for n, bands in enumerate(scan):
        used = set()
        for t in live:
            for i, (y0, y1, x0, x1) in enumerate(bands):
                if i not in used and abs(y0 - t["y0"]) < drift and abs(y1 - t["y1"]) < drift:
                    used.add(i)
                    t.update(end=n, hits=t["hits"] + 1, ya=min(t["ya"], y0), yb=max(t["yb"], y1),
                             xa=min(t["xa"], x0), xb=max(t["xb"], x1))
                    break
        done += [t for t in live if n - t["end"] > gap]
        live = [t for t in live if n - t["end"] <= gap]
        live += [dict(start=n, end=n, hits=1, y0=y0, y1=y1, ya=y0, yb=y1, xa=x0, xb=x1)
                 for i, (y0, y1, x0, x1) in enumerate(bands) if i not in used]
    return sorted((t for t in done + live if t["hits"] >= min_frames), key=lambda t: t["start"])


def med(E, lo, hi):
    v = [E[n] for n in range(lo, hi + 1) if n in E]
    return float(np.median(v)) if v else 0.0


def refine(c, E, win):
    s, e = c["start"], c["end"]
    on = med(E, s, e)
    thr = (on + min(med(E, s - win, s - 1), med(E, e + 1, e + win))) / 2
    hit = lambda n: n in E and E[n] >= thr
    if hit(s):
        while s - 1 >= c["start"] - win and hit(s - 1):
            s -= 1
    else:
        while s < e and not hit(s):
            s += 1
    if hit(e):
        while e + 1 <= c["end"] + win and hit(e + 1):
            e += 1
    else:
        while e > s and not hit(e):
            e -= 1
    off = max(med(E, s - win, s - 1), med(E, e + 1, e + win))
    c.update(scan=(c["start"], c["end"]), start=s, end=e, on=med(E, s, e), off=off,
             open_start=hit(s - 1), open_end=hit(e + 1))


def label(num, scale):
    ds = [np.array([int(ch) for ch in DIGITS[int(d)]]).reshape(5, 3) for d in str(num)]
    g = np.hstack([np.pad(d, ((0, 0), (0, 1))) for d in ds])
    return np.kron(g, np.ones((scale, scale), np.uint8)) * 255


def write_sheets(path, cands, W, H, N, outdir):
    os.makedirs(outdir, exist_ok=True)
    want = {}
    for i, c in enumerate(cands):
        for k, n in enumerate((max(0, c["start"] - 1), (c["start"] + c["end"]) // 2,
                               min(N - 1, c["end"] + 1))):
            want.setdefault(n, []).append((i, k))
    crops = {}
    for n, f in enumerate(gray(path, W, H)):
        for i, k in want.get(n, ()):
            c = cands[i]
            crops[i, k] = f[max(0, c["ya"] - SHEET_ROWS):c["yb"] + SHEET_ROWS + 1].astype(np.uint8)
    names = []
    for p0 in range(0, len(cands), PER_SHEET):
        strips = []
        for i in range(p0, min(p0 + PER_SHEET, len(cands))):
            panels = [crops[i, k] for k in range(3)]
            ht = panels[0].shape[0]
            tag = np.zeros((ht, 120), np.uint8)
            lab = label(i + 1, 8)[:ht, :100]
            y = (ht - lab.shape[0]) // 2
            tag[y:y + lab.shape[0], 14:14 + lab.shape[1]] = lab
            sep = np.full((ht, 12), 96, np.uint8)
            strips += [np.hstack([tag, panels[0], sep, panels[1], sep, panels[2]]),
                       np.full((12, 120 + 3 * W + 24), 255, np.uint8)]
        img = np.vstack(strips)
        name = os.path.join(outdir, f"captions-{p0 // PER_SHEET + 1:02d}.jpg")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray",
                        "-s", f"{img.shape[1]}x{img.shape[0]}", "-i", "-",
                        "-vf", "scale=iw/2:-2", "-q:v", "3", name], input=img.tobytes(), check=True)
        names.append(name)
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source"); ap.add_argument("captions")
    ap.add_argument("--sheet"); g = ap.add_mutually_exclusive_group()
    g.add_argument("--scan"); g.add_argument("--save-scan")
    a = ap.parse_args()

    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=width,height,r_frame_rate,nb_read_packets",
                          "-of", "json", a.source], capture_output=True, text=True, check=True)
    s = json.loads(out.stdout)["streams"][0]
    W, H, N = s["width"], s["height"], int(s["nb_read_packets"])
    num, den = map(int, s["r_frame_rate"].split("/"))
    fps = num / den
    kt, ky = fps / 30, H / 1920
    min_frames, gap, win = max(2, round(MIN_FRAMES * kt)), round(GAP * kt), round(WIN * kt)
    drift, min_h, max_h = DRIFT * ky, MIN_H * ky, MAX_H * ky

    if a.scan:
        scan = [[] for _ in range(N)]
        for t, bands in json.load(open(a.scan)):
            if round(t * fps) < N:
                scan[round(t * fps)] = bands
    else:
        scan = [scan_bands(f) for f in gray(a.source, W, H)]
        if a.save_scan:
            json.dump([[round(n / fps, 3), b] for n, b in enumerate(scan)], open(a.save_scan, "w"))
    cands = cluster(scan, min_frames, gap, drift)
    print(f"{W}x{H} {N}f {fps:g} fps: {sum(map(bool, scan))} frames with bands, "
          f"{len(cands)} candidates", file=sys.stderr)

    # Edge counts inside each candidate's box, 2 x WIN frames either side of it.
    E = [dict() for _ in cands]
    for n, f in enumerate(gray(a.source, W, H)):
        for i, c in enumerate(cands):
            if c["start"] - 2 * win <= n <= c["end"] + 2 * win:
                xa, xb = (c["xa"], c["xb"]) if c["xa"] >= 0 else (0, W)
                r = f[max(0, c["ya"] - BOX_PAD_Y):c["yb"] + BOX_PAD_Y + 1,
                      max(0, xa - BOX_PAD_X):xb + BOX_PAD_X + 2]
                E[i][n] = int(edges(r).sum())
    for c, e in zip(cands, E):
        refine(c, e, win)

    merged = []  # halves of one caption split by an occlusion meet again after refining
    for c in cands:
        m = merged[-1] if merged else None
        if m and c["start"] <= m["end"] + 1 and abs(c["ya"] - m["ya"]) < drift \
                and abs(c["yb"] - m["yb"]) < drift:
            m.update(end=max(m["end"], c["end"]), ya=min(m["ya"], c["ya"]),
                     yb=max(m["yb"], c["yb"]), xa=min(m["xa"], c["xa"]), xb=max(m["xb"], c["xb"]),
                     on=max(m["on"], c["on"]), off=max(m["off"], c["off"]),
                     open_end=c["open_end"], scan=(m["scan"][0], c["scan"][1]))
        else:
            merged.append(c)

    lines = [f"# CAPTIONS for composite-captions.py, drafted by build-captions.py from "
             f"{os.path.basename(a.source)}",
             "# start end y0 y1 name  (source frame numbers, inclusive; source rows)",
             "# Check every line on the sheets. '#?' lines were flagged; remove the '#?' to keep",
             "# one. Add any caption the scan missed by hand."]
    kept = 0
    for i, c in enumerate(merged):
        ht, contrast = c["yb"] - c["ya"], c["on"] / max(c["off"], 1.0)
        why = ([f"{ht} rows: too short"] if ht < min_h else []) + \
              ([f"{ht} rows: too tall for one line"] if ht > max_h else []) + \
              ([f"on/off contrast only {contrast:.1f}"] if contrast < MIN_CONTRAST else []) + \
              (["no clean cut-in"] if c["open_start"] else []) + \
              (["no clean cut-out"] if c["open_end"] else [])
        kept += not why
        lines.append(f"{'#? ' if why else ''}{c['start']} {c['end']} {c['ya']} {c['yb']} "
                     f"c{i + 1:02d}  # x{c['xa']}-{c['xb']} edges on {c['on']:.0f} off "
                     f"{c['off']:.0f}; scan {c['scan'][0]}-{c['scan'][1]}"
                     + (f"; {', '.join(why)}" if why else ""))
    open(a.captions, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[4:]), file=sys.stderr)
    print(f"{kept} captions kept, {len(merged) - kept} flagged -> {a.captions}", file=sys.stderr)
    if a.sheet:
        for name in write_sheets(a.source, merged, W, H, N, a.sheet):
            print("sheet:", name, file=sys.stderr)


if __name__ == "__main__":
    main()
