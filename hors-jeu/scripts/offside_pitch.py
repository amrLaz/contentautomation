#!/usr/bin/env python3
"""Offside check on a metric model of the pitch: every marking visible in the clip is used (penalty area, arc, halfway line, centre circle, touchline),
the offside line is the pitch line at the second-last defender's distance from the goal line, and the gap is measured in centimetres on the pitch.

usage: python offside_pitch.py clip.mov out.mp4 --cfg examples/clip2_pitch.json --pass-time 0.83
         [--defender X Y --attacker X Y]            pixels of the front-most body parts at ground level, read off a zoom (see --crops)
         [--next T GX GY AX AY ...]                 another source frame (the ball has just left): same two points, in that frame's pixels
         [--crops DIR]                              save 5x zooms of the two players to place the points by eye

Single camera: an estimate with its uncertainty, never an official decision.
The pitch axis u runs from the goal line the team attacks (u = 0), so 'attacker ahead' means a smaller u than the defender.
"""
import argparse, json, math, os, subprocess, sys
import numpy as np, cv2
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import pitch_fit as PF
from calibrate import grab_frames, register
from offside import Detector, analyse, tag, font

COL = {'off': (255, 59, 48, 255), 'on': (52, 211, 110, 255), 'close': (255, 159, 10, 255)}


def pts_to_pass(pts, M):
    q = np.hstack([np.asarray(pts, float).reshape(-1, 2), np.ones((len(np.atleast_2d(pts)), 1))]) @ M.T
    return q[:, :2] / q[:, 2:3]


def evaluate(r, G, A, sigma, M=np.eye(3), n=3000, seed=0):
    """Gap between the attacker and the defender along the pitch, in metres (positive = attacker ahead), with its spread from the placement error."""
    rng = np.random.default_rng(seed)
    def u(p): return PF.locate(r, pts_to_pass(p, M))
    uG, uA = u(G)[0], u(A)[0]
    noise = rng.normal(0, sigma, (n, 2, 2)); g = np.array(G, float) + noise[:, 0]; a = np.array(A, float) + noise[:, 1]
    d = PF.locate(r, pts_to_pass(g, M))[:, 0] - PF.locate(r, pts_to_pass(a, M))[:, 0]
    return {'uG': float(uG[0]), 'vG': float(uG[1]), 'uA': float(uA[0]), 'vA': float(uA[1]), 'gap': float(uG[0] - uA[0]), 'std': float(d.std()), 'p_ahead': float((d > 0).mean())}


def status(e, lo=0.10, hi=0.90):
    return 'off' if e['p_ahead'] >= hi else ('on' if e['p_ahead'] <= lo else 'close')


def cm(x): return f'{x * 100:+.0f} cm'


def auto_points(r, players):
    """Front-most defender and attacker from the detector's boxes: the box edge nearest the goal at foot level (arms may be included: check with --crops)."""
    def front(p): return (p['box'][0], p['box'][3])
    best = {}
    for team in ('defence', 'attack'):
        c = [p for p in players if p['team'] == team]
        if not c: sys.exit(f'No {team} player found.')
        best[team] = min(c, key=lambda p: PF.locate(r, [front(p)])[0, 0])
    return front(best['defence']), front(best['attack'])


def draw(im, r, evals, G, A, args):
    H, W = im.shape[:2]
    pil = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)).convert('RGBA'); ov = Image.new('RGBA', pil.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    st = status(evals[0]) if len(evals) == 1 else ('off' if all(status(e) == 'off' for e in evals) else 'on' if all(status(e) == 'on' for e in evals) else 'close')
    col = COL[st]; e0 = evals[0]
    def inside(p): return -300 < p[0] < W + 300 and -300 < p[1] < H + 300
    def poly(pts, fill, width):
        pts = [tuple(map(float, p)) for p in pts]
        for a, b in zip(pts, pts[1:]):
            if inside(a) and inside(b): d.line([a, b], fill=fill, width=width)
    for name, pts in PF.pitch_curves(r).items():  # the fitted model drawn back on the picture
        poly(pts, (90, 200, 255, 140), 2)
    # the offside line across the whole pitch, from the far to the near touchline, and its uncertainty band
    vs = np.linspace(-3, 71, 80); sg = max(e0['std'], 0.02)
    left = PF.image_of(r['Hn'], r['k1'], np.stack([np.full_like(vs, e0['uG'] - sg), vs], 1)); right = PF.image_of(r['Hn'], r['k1'], np.stack([np.full_like(vs, e0['uG'] + sg), vs], 1))
    mid = PF.image_of(r['Hn'], r['k1'], np.stack([np.full_like(vs, e0['uG']), vs], 1))
    ok = [i for i in range(len(vs)) if inside(mid[i])]
    if ok:
        i0, i1 = ok[0], ok[-1]
        d.polygon([tuple(p) for p in left[i0:i1 + 1]] + [tuple(p) for p in right[i0:i1 + 1][::-1]], fill=col[:3] + (60,))
        poly(mid[i0:i1 + 1], (255, 255, 255, 110), 14); poly(mid[i0:i1 + 1], (255, 255, 255, 255), 4)
    for p, c, lab in ((G, (255, 255, 255, 255), "pointe du pied du défenseur"), (A, col, 'partie du corps la plus avancée')):
        d.ellipse([p[0] - 9, p[1] - 9, p[0] + 9, p[1] + 9], outline=c, width=3); tag(d, (p[0] - 20, p[1] + (16 if lab.startswith('partie') else -42)), lab, c, 20)
    txt = {'off': 'HORS-JEU PROBABLE', 'on': 'EN JEU', 'close': 'TROP JUSTE POUR TRANCHER'}[st]
    tag(d, (50, 40), txt, col, 44)
    tag(d, (50, 112), "Estimation indicative, une seule caméra : pas une décision officielle.", (255, 255, 255, 240), 22, False)
    y = H - 60 - 40 * len(evals)
    tag(d, (50, y - 44), f"2e dernier défenseur à {e0['uG']:.1f} m de la ligne de but", (255, 255, 255, 255), 22, False)
    for k, (e, lab) in enumerate(zip(evals, args.labels)):
        tag(d, (50, y + 40 * k), f"{lab} : attaquant {cm(e['gap'])} (± {e['std'] * 100:.0f} cm)  {'devant' if e['gap'] > 0 else 'derrière'} la ligne", COL[status(e)], 22)
    return cv2.cvtColor(np.array(Image.alpha_composite(pil, ov).convert('RGB')), cv2.COLOR_RGB2BGR)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video'); ap.add_argument('out'); ap.add_argument('--cfg', required=True); ap.add_argument('--pass-time', type=float, required=True)
    ap.add_argument('--crop', default='1920:1080:0:180'); ap.add_argument('--defender', type=float, nargs=2); ap.add_argument('--attacker', type=float, nargs=2)
    ap.add_argument('--next', type=float, nargs=5, action='append', default=[], metavar=('T', 'GX', 'GY', 'AX', 'AY'))
    ap.add_argument('--sigma', type=float, nargs=2, help='placement error of a body part in pixels, x y (default 2.5 4 with --defender/--attacker, else 5 8)')
    ap.add_argument('--crops'); ap.add_argument('--hold', type=float, default=3.0); ap.add_argument('--json')
    ap.add_argument('--model', default=os.path.join(ROOT, 'models', 'yolox.onnx')); ap.add_argument('--red-hue', type=float, nargs=2, default=[0, 30])
    ap.add_argument('--green-hue', type=float, nargs=2, default=[34, 95]); ap.add_argument('--min-colour', type=float, default=0.35); ap.add_argument('--top', type=int, default=190)
    a = ap.parse_args()
    cfg = PF.load_cfg(a.cfg); r = PF.fit(a.video, a.pass_time, a.crop, cfg); im = r['frame']
    manual = a.defender is not None and a.attacker is not None
    if manual: G, A = tuple(a.defender), tuple(a.attacker)
    else:
        players, _ = analyse(im, a, Detector(a.model)); G, A = auto_points(r, players)
        print('front-most points taken from the detector boxes (arms may be included):', [round(v) for v in G], [round(v) for v in A])
    sigma = a.sigma or ([2.5, 4.0] if manual else [5.0, 8.0])
    evals = [evaluate(r, G, A, sigma)]; a.labels = [f'À la passe ({a.pass_time:.2f} s)']
    for t, gx, gy, ax, ay in a.next:  # later source frames: carry their pixels onto the pass frame first
        fr = grab_frames(a.video, [round(a.pass_time, 3), round(t, 3)], a.crop); M = register(fr, round(a.pass_time, 3))[round(t, 3)]
        evals.append(evaluate(r, (gx, gy), (ax, ay), sigma, M)); a.labels.append(f'Image suivante ({t:.2f} s)')
    for lab, e in zip(a.labels, evals):
        print(f"{lab}: defender u={e['uG']:.2f} m, attacker u={e['uA']:.2f} m -> attacker {cm(e['gap'])} +- {e['std'] * 100:.0f} cm, P(ahead)={e['p_ahead'] * 100:.0f}% -> {status(e)}")
    frame = draw(im, r, evals, G, A, a)
    png = os.path.splitext(a.out)[0] + '.png'; cv2.imwrite(png, frame); print('saved', png)
    if a.json: json.dump({'pass_time': a.pass_time, 'evaluations': [{'label': l, **e, 'status': status(e)} for l, e in zip(a.labels, evals)]}, open(a.json, 'w'), indent=1)
    if a.crops:
        os.makedirs(a.crops, exist_ok=True)
        for name, p in (('defender', G), ('attacker', A)):
            x, y = int(p[0]), int(p[1]); c = im[max(0, y - 90):y + 50, max(0, x - 110):x + 110].copy(); c = cv2.resize(c, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
            cv2.circle(c, (110 * 5 if x >= 110 else x * 5, (90 if y >= 90 else y) * 5), 12, (255, 255, 255), 2); cv2.imwrite(os.path.join(a.crops, f'{name}.png'), c)
    w, h = frame.shape[1], frame.shape[0]; fps = 30
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps), '-i', '-', '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', a.out], stdin=subprocess.PIPE)
    cw, ch, cx, cy = [int(v) for v in a.crop.split(':')]
    rd = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', a.video, '-vf', f'crop={cw}:{ch}:{cx}:{cy},fps={fps}', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], stdout=subprocess.PIPE, bufsize=10 ** 8)
    i = 0; n_pass = int(round(a.pass_time * fps)); done = False
    while True:
        b = rd.stdout.read(w * h * 3)
        if len(b) < w * h * 3: break
        if i < n_pass: enc.stdin.write(b)
        else:
            if not done:
                for k in range(int(a.hold * fps)):
                    prog = min(1.0, k / (0.35 * fps)); enc.stdin.write((frame if prog >= 1 else cv2.addWeighted(im, 1 - prog, frame, prog, 0)).tobytes())
                done = True
            enc.stdin.write(b)
        i += 1
    enc.stdin.close(); enc.wait(); print('Done:', a.out)


if __name__ == '__main__':
    main()
