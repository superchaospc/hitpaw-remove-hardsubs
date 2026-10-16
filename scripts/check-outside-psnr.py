#!/usr/bin/env python3
"""Acceptance check: did compositing change any pixel outside the caption rectangles?

Usage:
  check-outside-psnr.py SOURCE RESTORED [CONTROL]

RESTORED  output of composite-captions.py; RESTORED.rects.json says where it patched
CONTROL   SOURCE re-encoded with the composite's x264 settings and nothing else changed.
          Created when the path does not exist (default: RESTORED.control.mp4).

Outside the rectangles the composite should be a plain re-encode of the source, so there its
PSNR against the source must match the control's. A pipeline that touches every pixel (an
rgb24 round trip, or colour tags only on the output side) scores several dB lower (43 dB
against 47) and shifts mean Y by about -1.7, while the caption band itself looks fine.
Compares raw Y, U and V planes, never format=gray, which converts tagged and untagged files
differently. Passes when every plane is within 0.5 dB of the control and mean Y is within
0.5 levels of the control's. Needs numpy and ffmpeg/ffprobe.
"""
import json, os, subprocess, sys
import numpy as np

MAX_DB_BELOW, MAX_Y_SHIFT = 0.5, 0.5


def yuv(path, w, h):
    p = subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-map", "0:v:0",
                          "-vf", "format=yuv420p", "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    size = w * h * 3 // 2
    try:
        while True:
            b = p.stdout.read(size)
            if len(b) < size:
                return
            a = np.frombuffer(b, np.uint8)
            yield (a[:w * h].reshape(h, w), a[w * h:w * h * 5 // 4].reshape(h // 2, w // 2),
                   a[w * h * 5 // 4:].reshape(h // 2, w // 2))
    finally:
        p.kill(); p.wait()


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    src, res = sys.argv[1:3]
    ctl = sys.argv[3] if len(sys.argv) == 4 else res + ".control.mp4"
    rects = json.load(open(res + ".rects.json"))["rects"]
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                   "-show_entries", "stream=width,height", "-of", "json", src],
                                  capture_output=True, text=True, check=True).stdout)["streams"][0]
    W, H = s["width"], s["height"]
    if not os.path.exists(ctl):
        print("making control:", ctl, file=sys.stderr)
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src, "-map", "0:v:0",
                        "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
                        ctl], check=True)

    names = ("restored", "control")
    sse = np.zeros((2, 3)); cnt = np.zeros(3); shift = np.zeros(2)
    key, masks, frames = None, None, 0
    for n, (sf, *fs) in enumerate(zip(yuv(src, W, H), yuv(res, W, H), yuv(ctl, W, H))):
        act = tuple(i for i, r in enumerate(rects) if r["frames"][0] <= n <= r["frames"][1])
        if act != key:
            masks = []
            for k, p in enumerate(sf):
                sx = 1 if k == 0 else 2
                m = np.ones(p.shape, bool)
                for i in act:
                    (xa, xb), (ya, yb) = rects[i]["x"], rects[i]["y"]
                    m[ya // sx:yb // sx, xa // sx:xb // sx] = False
                masks.append(m)
            key = act
        for k, (sp, m) in enumerate(zip(sf, masks)):
            ref = sp[m].astype(np.float64)
            cnt[k] += ref.size
            for j, f in enumerate(fs):
                d = f[k][m] - ref
                sse[j, k] += float((d * d).sum())
                if k == 0:
                    shift[j] += float(d.sum())
        frames = n + 1

    db = 10 * np.log10(255 * 255 * cnt / np.maximum(sse, 1e-9))
    my = shift / cnt[0]
    print(f"outside the {len(rects)} patch rectangles, {frames} frames, against {os.path.basename(src)}")
    print("            Y dB    U dB    V dB   mean dY")
    for j, name in enumerate(names):
        print(f"{name:9s} {db[j, 0]:7.2f} {db[j, 1]:7.2f} {db[j, 2]:7.2f} {my[j]:+8.2f}")
    worst = float((db[1] - db[0]).max())
    ok = worst <= MAX_DB_BELOW and abs(my[0] - my[1]) <= MAX_Y_SHIFT
    print(("PASS" if ok else "FAIL") + f": restored is at most {max(worst, 0):.2f} dB below the "
          f"control on any plane (limit {MAX_DB_BELOW}); mean Y differs by "
          f"{my[0] - my[1]:+.2f} (limit {MAX_Y_SHIFT})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
