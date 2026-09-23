#!/usr/bin/env python3
"""Paste HitPaw's cleaned pixels back onto the source, only where a caption was.

Usage:
  composite-mask.py SOURCE HITPAW OUTPUT [--band Y0 Y1] [--offset K]

SOURCE   original video (any size; its resolution, frame rate, frame count and audio are kept)
HITPAW   the downloaded HitPaw result (usually 608x1080)
OUTPUT   restored video at the source resolution; conform it afterwards with conform-vertical.sh
--band   source rows covered by the box you drew in HitPaw (default: whole frame)
--offset HitPaw frame n+K pairs with source frame n (default: measured automatically)

The per-frame row mask is the union of two detectors, each padded 30 rows and 6 frames:
  1. edge scan on the source (outlined captions; the detector in references/subtitle-scan.md)
  2. source-vs-HitPaw difference: rows where many pixels changed sharply are rows HitPaw
     repainted. This catches plain white captions with no dark stroke, which the edge scan
     misses entirely.
Outside the mask every pixel is the source's, so resolution is only lost on caption rows,
and only on the frames where a caption shows. Needs numpy and ffmpeg/ffprobe.
"""
import argparse, json, subprocess, sys
import numpy as np

EDGE_DIFF, EDGE_ROW, BAND_GAP, BAND_MIN = 70, 25, 12, 12   # subtitle-scan.md thresholds
PIX_DIFF, ROW_PIX = 45, 10                                # difference-mask thresholds
ROW_PAD, T_PAD, FEATHER = 30, 6, 12


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                          "-show_entries", "stream=width,height,r_frame_rate,nb_read_packets",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    return s["width"], s["height"], s["r_frame_rate"], int(s["nb_read_packets"])


def frames(path, w, h, ch, vf=""):
    pix = "rgb24" if ch == 3 else "gray"
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-vf",
                          f"{vf}format={pix}", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    size = w * h * ch
    try:
        while True:
            b = p.stdout.read(size)
            if len(b) < size:
                return
            a = np.frombuffer(b, np.uint8)
            yield a.reshape(h, w, ch) if ch == 3 else a.reshape(h, w)
    finally:  # a reader abandoned early (alignment sampling) must not spew broken-pipe errors
        p.kill(); p.wait()


def edge_rows(gray):
    tr = (np.abs(np.diff(gray.astype(np.int16), axis=1)) > EDGE_DIFF).sum(axis=1)
    rows = np.zeros(gray.shape[0], bool)
    ys = np.where(tr >= EDGE_ROW)[0]
    if len(ys):
        start = prev = ys[0]
        for y in list(ys[1:]) + [10**9]:
            if y - prev > BAND_GAP:
                if prev - start >= BAND_MIN:
                    rows[max(0, start - ROW_PAD):prev + ROW_PAD + 1] = True
                start = y
            prev = y
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source"); ap.add_argument("hitpaw"); ap.add_argument("output")
    ap.add_argument("--band", nargs=2, type=int)
    ap.add_argument("--offset", type=int)
    a = ap.parse_args()

    W, H, rate, N = probe(a.source)
    w, h, _, _ = probe(a.hitpaw)
    y0, y1 = a.band if a.band else (0, H)
    small = f"scale={w}:{h}:flags=area,"

    # Alignment: HitPaw can drop a frame. Compare the first 150 frames at offsets -2..2.
    if a.offset is None:
        S = [f.astype(np.int16) for _, f in zip(range(150), frames(a.source, w, h, 1, small))]
        P = [f.astype(np.int16) for _, f in zip(range(152), frames(a.hitpaw, w, h, 1))]
        score = {}
        for k in range(-2, 3):
            pairs = [(S[n], P[n + k]) for n in range(len(S)) if 0 <= n + k < len(P)]
            score[k] = np.mean([np.abs(s - p).mean() for s, p in pairs])
        a.offset = min(score, key=score.get)
        print("alignment MAD by offset:", {k: round(v, 2) for k, v in score.items()},
              "-> offset", a.offset, file=sys.stderr)

    # Pass 1: row masks from both detectors.
    edge = np.zeros((N, H), bool)
    diff = np.zeros((N, H), bool)
    hp = frames(a.hitpaw, w, h, 1)
    for _ in range(max(0, a.offset)):
        next(hp, None)
    for n, (s_full, s_small) in enumerate(zip(frames(a.source, W, H, 1),
                                              frames(a.source, w, h, 1, small))):
        if n >= N:
            break
        edge[n] = edge_rows(s_full)
        p = next(hp, None) if n + a.offset >= 0 else None
        if p is not None:
            cnt = (np.abs(s_small.astype(np.int16) - p.astype(np.int16)) > PIX_DIFF).sum(axis=1)
            for r in np.where(cnt >= ROW_PIX)[0]:
                y = int(r * H / h)
                diff[n, max(0, y - ROW_PAD):y + int(H / h) + ROW_PAD + 1] = True
    for m in (edge, diff):
        m[:, :y0] = False
        m[:, y1:] = False
    raw = edge | diff
    mask = np.zeros_like(raw)
    for n in range(N):
        mask[n] = raw[max(0, n - T_PAD):n + T_PAD + 1].any(axis=0)
    print(f"frames {N}, masked {int(mask.any(axis=1).sum())} "
          f"(edge-only {int((edge & ~diff).any(axis=1).sum())}, "
          f"diff-only {int((diff & ~edge).any(axis=1).sum())})", file=sys.stderr)

    # Pass 2: composite. Never add -shortest: source audio is often a few ms shorter than the
    # video and -shortest silently drops the last frames.
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", rate, "-i", "-", "-i", a.source,
                            "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-crf", "16",
                            "-preset", "slow", "-pix_fmt", "yuv420p", "-c:a", "copy",
                            "-frames:v", str(N), a.output], stdin=subprocess.PIPE)
    k = np.ones(2 * FEATHER + 1) / (2 * FEATHER + 1)
    hp = frames(a.hitpaw, W, H, 3, f"scale={W}:{H}:flags=lanczos,")
    for _ in range(max(0, a.offset)):
        next(hp, None)
    last = None
    for n, s in enumerate(frames(a.source, W, H, 3)):
        if n >= N:
            break
        p = next(hp, None) if n + a.offset >= 0 else None
        last = p if p is not None else last
        p = p if p is not None else last
        if p is not None and mask[n].any():
            alpha = np.convolve(mask[n].astype(float), k, mode="same")[:, None, None]
            s = (s * (1 - alpha) + p * alpha).astype(np.uint8)
        enc.stdin.write(s.tobytes())
    enc.stdin.close()
    sys.exit(enc.wait())


if __name__ == "__main__":
    main()
