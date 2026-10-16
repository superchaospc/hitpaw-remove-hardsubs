#!/usr/bin/env python3
"""Paste HitPaw's cleaned pixels onto the source inside one feathered rectangle per caption.

Usage:
  composite-captions.py SOURCE HITPAW CAPTIONS OUTPUT [--box X0 X1 Y0 Y1] [--offset K]

SOURCE    original video; its resolution, frame rate, frame count, colour tags and audio are kept
HITPAW    the downloaded HitPaw result (usually 608x1080)
CAPTIONS  one confirmed caption per line: START END Y0 Y1 [NAME], source frame numbers (inclusive)
          and source rows; '#' starts a comment. build-captions.py writes a draft to review.
OUTPUT    restored video at the source resolution; conform it afterwards with conform-vertical.sh
--box     the rectangle drawn in HitPaw, in source pixels. Patch rectangles are clamped inside it:
          outside the box HitPaw only returns a downscaled copy of the source.
--offset  source frame n pairs with HitPaw frame n-K (default: measured over -2..2)

Each caption's rectangle is where HitPaw changed pixels near that caption's rows during that
caption's frames, padded 40 px sideways, 30 rows vertically and 3 frames in time, feathered 12 px.
Outside the rectangles every pixel is the source's. The Y, U and V planes are blended directly
(no RGB round trip), and the raw pipe is colour-tagged on its INPUT side, so ffmpeg never
range-converts the untouched pixels. Writes OUTPUT.rects.json for check-outside-psnr.py, and
reports rows HitPaw repainted outside every listed caption: a missed caption, or texture noise.
Needs numpy and ffmpeg/ffprobe.
"""
import argparse, json, subprocess, sys
import numpy as np

PIX_DIFF, ROW_PIX, COL_PIX = 39, 10, 2  # changed pixel: raw |dY| > 39 (= 45 on full-range grey);
                                        # a row needs 10 of them, a column 2
SEARCH = 60                             # source rows searched above and below each caption
PAD_X, PAD_Y, T_PAD, FEATHER = 40, 30, 3, 12
STRAY_T, STRAY_ROWS, STRAY_RUN = 6, 6, 5  # stray repaint: >= 6 rows changed, >= 6 frames from a
                                          # caption; runs of >= 5 such frames are reported
STRAY_GAP, STRAY_DRIFT = 3, 40            # band rows (HitPaw scale) / run drift (source rows)
CAPTION_LIKE = (20, 120)                  # a run this long (frames at 30 fps) on this few rows
                                          # (of 1920) looks like a missed caption or sticker
SAMPLE_EVERY = 23                         # alignment samples every 23rd source frame


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=width,height,r_frame_rate,nb_read_packets,"
                          "color_range,color_space,color_transfer,color_primaries",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def yuv(path, w, h, vf=""):
    """Yield (Y, U, V) uint8 planes of yuv420p frames: raw values, no range conversion."""
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-map", "0:v:0",
                          "-vf", f"{vf}format=yuv420p", "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE)
    size = w * h * 3 // 2
    try:
        while True:
            b = p.stdout.read(size)
            if len(b) < size:
                return
            a = np.frombuffer(b, np.uint8)
            yield (a[:w * h].reshape(h, w), a[w * h:w * h * 5 // 4].reshape(h // 2, w // 2),
                   a[w * h * 5 // 4:].reshape(h // 2, w // 2))
    finally:  # a reader abandoned early must not leave ffmpeg writing into a dead pipe
        p.kill(); p.wait()


def luma(path, w, h, vf=""):
    for f in yuv(path, w, h, vf):
        yield f[0].astype(np.int16)


def psnr(a, b):
    # float: an int16 square overflows once a caption pixel differs by more than 181
    m = float(((a.astype(np.float64) - b) ** 2).mean())
    return 99.0 if m == 0 else 10 * np.log10(255 * 255 / m)


def aligned(gen, n_out, off, nh):
    """Yield the HitPaw frame for source frames 0..n_out-1 (source n <-> HitPaw n-off, clamped)."""
    j, last = 0, None
    for n in range(n_out):
        want = min(max(n - off, 0), nh - 1)
        while j <= want:
            nxt = next(gen, None)
            if nxt is None:
                break
            last, j = nxt, j + 1
        yield last


def read_captions(path):
    caps = []
    for line in open(path, encoding="utf-8"):
        t = line.split("#", 1)[0].split()
        if not t:
            continue
        a, b, y0, y1 = map(int, t[:4])
        caps.append((a, b, y0, y1, " ".join(t[4:]) or f"c{len(caps) + 1:02d}"))
    return caps


def strongest_band(ys, cnt):
    """Rows (y0, y1) of the band of changed rows holding the most changed pixels."""
    best, start = None, ys[0]
    for prev, y in zip(ys, list(ys[1:]) + [None]):
        if y is None or y - prev > STRAY_GAP:
            score = int(cnt[start:prev + 1].sum())
            if best is None or score > best[2]:
                best = (int(start), int(prev) + 1, score)
            start = y
    return best[:2]


def ramp(n, f):
    i = np.arange(n)
    return np.clip(np.minimum(i, n - 1 - i) / f, 0, 1)


def alpha(rects, shape, sx):
    """Feathered alpha for the rectangles (x0, x1, y0, y1) on a plane subsampled by sx."""
    al = np.zeros(shape)
    for xa, xb, ya, yb in rects:
        xa, xb, ya, yb = xa // sx, xb // sx, ya // sx, yb // sx
        sub = np.outer(ramp(yb - ya, FEATHER / sx), ramp(xb - xa, FEATHER / sx))
        al[ya:yb, xa:xb] = np.maximum(al[ya:yb, xa:xb], sub)
    return al


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source"); ap.add_argument("hitpaw"); ap.add_argument("captions")
    ap.add_argument("output")
    ap.add_argument("--box", nargs=4, type=int, metavar=("X0", "X1", "Y0", "Y1"))
    ap.add_argument("--offset", type=int)
    a = ap.parse_args()

    s0, h0 = probe(a.source), probe(a.hitpaw)
    W, H, N, rate = s0["width"], s0["height"], int(s0["nb_read_packets"]), s0["r_frame_rate"]
    w, h, NH = h0["width"], h0["height"], int(h0["nb_read_packets"])
    caps = read_captions(a.captions)
    small = f"scale={w}:{h}:flags=area,"
    print(f"source {W}x{H} {N}f  hitpaw {w}x{h} {NH}f  captions {len(caps)}", file=sys.stderr)

    # Alignment: HitPaw can drop or add a frame. Score offsets -2..2 on sampled frames.
    if a.offset is None:
        samp = set(range(0, N, SAMPLE_EVERY))
        S = {n: f for n, f in enumerate(luma(a.source, w, h, small)) if n in samp}
        P = {j: f for j, f in enumerate(luma(a.hitpaw, w, h))
             if any(j + k in samp for k in range(-2, 3))}
        scores = {}
        for k in range(-2, 3):  # source frame n <-> HitPaw frame n-k
            scores[k] = float(np.mean([psnr(S[n], P[n - k]) for n in S if n - k in P]))
        a.offset = max(scores, key=scores.get)
        print("alignment PSNR by offset:", {k: round(v, 2) for k, v in scores.items()},
              "-> offset", a.offset, file=sys.stderr)
        del S, P
    else:
        scores = None

    # Pass 1: each caption's changed extent, and rows repainted away from every caption.
    sy = h / H
    ext = [None] * len(caps)
    stray = []
    for n, (sf, pf) in enumerate(zip(luma(a.source, w, h, small),
                                     aligned(luma(a.hitpaw, w, h), N, a.offset, NH))):
        d = np.abs(sf - pf) > PIX_DIFF
        cov = np.zeros(h, bool)
        for i, (c0, c1, y0, y1, _) in enumerate(caps):
            r0, r1 = max(0, int((y0 - SEARCH) * sy)), min(h, int((y1 + SEARCH) * sy) + 1)
            if c0 - STRAY_T <= n <= c1 + STRAY_T:
                cov[r0:r1] = True
            if not c0 <= n <= c1:
                continue
            m = d[r0:r1]
            rr = np.where(m.sum(axis=1) >= ROW_PIX)[0]
            cc = np.where(m.sum(axis=0) >= COL_PIX)[0]
            if len(rr) == 0 or len(cc) == 0:
                continue
            v = [int(cc.min() * W / w), int((cc.max() + 1) * W / w),
                 int((rr.min() + r0) / sy), int((rr.max() + r0 + 1) / sy)]
            e = ext[i]
            ext[i] = v if e is None else [min(e[0], v[0]), max(e[1], v[1]),
                                          min(e[2], v[2]), max(e[3], v[3])]
        cov[:2] = cov[-2:] = True  # the outermost rows differ from scaling alone
        cnt = d.sum(axis=1)
        ys = np.where((cnt >= ROW_PIX) & ~cov)[0]
        if len(ys) >= STRAY_ROWS:
            y0, y1 = strongest_band(ys, cnt)
            stray.append((n, int(y0 / sy), int(y1 / sy)))

    rects = []
    for (c0, c1, y0, y1, name), e in zip(caps, ext):
        if e is None:
            print(f"WARNING {name} (frames {c0}-{c1}, rows {y0}-{y1}): HitPaw changed nothing "
                  "there. The caption was not removed, or its frames/rows are wrong; patching "
                  "full width.", file=sys.stderr)
            e = [PAD_X, W - PAD_X, y0, y1]
        xa, xb = max(0, e[0] - PAD_X), min(W, e[1] + PAD_X)
        ya, yb = max(0, min(y0, e[2]) - PAD_Y), min(H, max(y1, e[3]) + PAD_Y)
        if a.box:
            xa, xb = max(xa, a.box[0]), min(xb, a.box[1])
            ya, yb = max(ya, a.box[2]), min(yb, a.box[3])
        rects.append({"name": name, "frames": [max(0, c0 - T_PAD), min(N - 1, c1 + T_PAD)],
                      "x": [xa, xb], "y": [ya, yb]})
        r = rects[-1]
        print("rect %-12s frames %d-%d x%d-%d y%d-%d" % (name, *r["frames"], *r["x"], *r["y"]),
              file=sys.stderr)

    runs = []  # group stray frames whose strongest band stays put into runs for review
    for n, ya, yb in stray:
        r = runs[-1] if runs else None
        if r and n - r[1] <= 3 and abs(ya - r[5]) < STRAY_DRIFT:
            r[1], r[2], r[3], r[4], r[5] = n, min(r[2], ya), max(r[3], yb), r[4] + 1, ya
        else:
            runs.append([n, n, ya, yb, 1, ya])
    runs = [r[:5] for r in runs if r[4] >= STRAY_RUN]
    num, den = map(int, rate.split("/"))
    long_run, narrow = round(CAPTION_LIKE[0] * num / den / 30), CAPTION_LIKE[1] * H / 1920
    print(f"repainted outside every caption, runs of >= {STRAY_RUN} frames: {len(runs)}",
          file=sys.stderr)
    for r in runs:
        like = r[4] >= long_run and r[3] - r[2] <= narrow
        print("  frames %d-%d rows %d-%d (%d frames)" % tuple(r)
              + ("  <- caption-like: look at it" if like else ""), file=sys.stderr)
    with open(a.output + ".rects.json", "w") as f:
        json.dump({"offset": a.offset, "offset_psnr": scores, "box": a.box, "rects": rects,
                   "stray_runs": runs}, f, indent=1)

    # Pass 2: blend. Tag the raw INPUT with the source's colour description (limited-range
    # BT.709 when the source has none); tagging only the output makes ffmpeg range-convert
    # every pixel. Never add -shortest: source audio is often a few ms shorter than the video,
    # and -shortest silently drops the last frames.
    tags = []
    for opt, key, default in (("-color_range", "color_range", "tv"),
                              ("-colorspace", "color_space", "bt709"),
                              ("-color_trc", "color_transfer", "bt709"),
                              ("-color_primaries", "color_primaries", "bt709")):
        v = s0.get(key)
        tags += [opt, v if v and v != "unknown" else default]
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "yuv420p",
                            "-s", f"{W}x{H}", "-r", rate, *tags, "-i", "-", "-i", a.source,
                            "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", "16",
                            "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "copy",
                            "-frames:v", str(N), a.output], stdin=subprocess.PIPE)
    patched, key, als = 0, None, None
    hp = aligned(yuv(a.hitpaw, W, H, f"scale={W}:{H}:flags=lanczos,"), N, a.offset, NH)
    for n, (sf, pf) in enumerate(zip(yuv(a.source, W, H), hp)):
        act = tuple(i for i, r in enumerate(rects) if r["frames"][0] <= n <= r["frames"][1])
        if act:
            if act != key:  # the active set changes rarely; reuse its alpha planes
                boxes = [rects[i]["x"] + rects[i]["y"] for i in act]
                als = [alpha(boxes, p.shape, 1 if k == 0 else 2) for k, p in enumerate(sf)]
                key = act
            sf = [(s * (1 - al) + p * al + 0.5).astype(np.uint8)
                  for s, p, al in zip(sf, pf, als)]
            patched += 1
        enc.stdin.write(b"".join(np.ascontiguousarray(x).tobytes() for x in sf))
    enc.stdin.close()
    rc = enc.wait()
    print(f"frames patched: {patched} of {N}; rectangles in {a.output}.rects.json",
          file=sys.stderr)
    sys.exit(rc)


if __name__ == "__main__":
    main()
