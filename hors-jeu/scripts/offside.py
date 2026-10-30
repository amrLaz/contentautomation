#!/usr/bin/env python3
"""Indicative offside check on one moment of a football clip, with the line drawn on a freeze frame.

usage: python offside.py clip.mp4 out.mp4 --pass-time 0.83 --attack left [--crop 1920:1080:0:180]

How it works (single camera, so the result is an estimate, never an official decision):
  1. players and ball are detected on the frame of the pass (detect.py, YOLOX over tiles)
  2. each player gets a team from the hue of the jersey (red / green); officials (dark kit, little colour) are dropped
  3. the offside line is drawn through the front-most body part of the second-last defender, in the direction of the goal line
     (--line-angle, 0 = vertical on screen, which is what a side-on camera shows; measure it with measure_goal_line.py)
  4. every attacker is compared with that line; the distance in metres comes from the players' own height (1.80 m)
The goalkeeper is assumed to be the last defender; if he is out of frame, the front-most visible defender is the second-last.
"""
import argparse, json, math, os, subprocess, sys
import cv2, numpy as np
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detect import Detector

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
FONT = os.path.join(ROOT, 'fonts', 'Inter.ttf')


def font(size, bold=True):
    f = ImageFont.truetype(FONT, int(size))
    try: f.set_variation_by_axes([32, 800 if bold else 500])
    except Exception: pass
    return f


def jersey(im, box):
    """-> (hue, share of strongly coloured pixels) of the torso."""
    x0, y0, x1, y1 = [max(0, int(v)) for v in box]; h = y1 - y0
    c = im[y0 + int(h * .15):y0 + int(h * .55), x0 + int((x1 - x0) * .2):x1 - int((x1 - x0) * .2)]
    if c.size == 0: return -1, 0.0
    hsv = cv2.cvtColor(c, cv2.COLOR_BGR2HSV).reshape(-1, 3); m = hsv[(hsv[:, 1] > 70) & (hsv[:, 2] > 60)]
    return (float(np.median(m[:, 0])) if len(m) > 8 else -1), len(m) / len(hsv)


def team_of(hue, share, red, green, min_share):
    if hue < 0 or share < min_share: return 'official'
    if red[0] <= hue <= red[1]: return 'attack'
    if green[0] <= hue <= green[1]: return 'defence'
    return 'other'


def grab(video, t, crop, fps_out=60):
    w, h, x, y = [int(v) for v in crop.split(':')]
    p = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', video, '-frames:v', '1', '-vf', f'crop={w}:{h}:{x}:{y}', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                       capture_output=True, check=True).stdout
    return cv2.imdecode(np.frombuffer(p, np.uint8), 1)


def analyse(im, args, det):
    dets = det(im, y0=args.top, conf=0.3)
    players = []
    for d in dets:
        if d['cls'] != 'person': continue
        x0, y0, x1, y1 = d['box']
        if y1 < args.top + 5: continue
        hue, share = jersey(im, d['box']); t = team_of(hue, share, args.red_hue, args.green_hue, args.min_colour)
        players.append({'box': d['box'], 'team': t, 'hue': hue, 'share': share, 'h': y1 - y0})
    balls = sorted([d for d in dets if d['cls'] == 'ball'], key=lambda d: -d['score'])
    return players, balls


def front(box, direction):  # the most advanced x of a box, in the attacking direction
    return box[0] if direction == 'left' else box[2]


def tag(d, xy, text, fill, size=24, bold=True):
    """A label on a dark rounded background, readable on any picture."""
    f = font(size, bold); l, t, r, b = d.textbbox(xy, text, font=f)
    d.rounded_rectangle([l - 10, t - 6, r + 10, b + 6], 10, fill=(0, 0, 0, 185)); d.text(xy, text, font=f, fill=fill)


def pick_ball(balls, players, max_px=90):
    """The ball is the detection closest to a player's feet; a ball-like blob far from every player (a marking, a board) is ignored."""
    best = None
    for b in balls:
        bx, by = (b['box'][0] + b['box'][2]) / 2, (b['box'][1] + b['box'][3]) / 2
        dist = min((math.hypot(bx - (p['box'][0] + p['box'][2]) / 2, by - p['box'][3]) for p in players), default=1e9)
        if dist <= max_px and (best is None or dist < best[0]): best = (dist, b)
    return best[1] if best else None


def line_x(P, vp, y):
    """x of the line through P and the vanishing point vp (the lines perpendicular to the touchlines) at height y."""
    if vp is None: return P[0]
    return P[0] + (vp[0] - P[0]) / (vp[1] - P[1]) * (y - P[1])


def verdict(players, direction, vp, ref_err=8.0, det_err=8.0, vp_err=(60.0, 90.0)):
    """Compare every attacker with the second-last defender's front-most point, along the line through that point and the vanishing point.
    The gap is measured at the attacker's own depth, in pixels and in metres (the players' height, 1.80 m, gives the scale there)."""
    sign = -1 if direction == 'left' else 1
    defs = [p for p in players if p['team'] == 'defence']; atts = [p for p in players if p['team'] == 'attack']
    if not defs or not atts: return None
    defs.sort(key=lambda p: -sign * front(p['box'], direction))
    last = defs[0]; P = (front(last['box'], direction), last['box'][3]); out = []
    for a in atts:
        ax, ay = front(a['box'], direction), a['box'][3]; gap = sign * (ax - line_x(P, vp, ay))
        slope = abs((vp[0] - P[0]) / (vp[1] - P[1])) if vp else 0.0
        vp_shift = 0.0
        if vp:  # how far the line moves at the attacker's depth if the vanishing point is off by vp_err
            for dx, dy in ((vp_err[0], 0), (-vp_err[0], 0), (0, vp_err[1]), (0, -vp_err[1])):
                vp_shift = max(vp_shift, abs(line_x(P, (vp[0] + dx, vp[1] + dy), ay) - line_x(P, vp, ay)))
        sigma = math.sqrt((ref_err * (1 + slope)) ** 2 + det_err ** 2 + vp_shift ** 2)  # px
        hm = 0.5 * (a['h'] + last['h']); out.append({'att': a, 'gap_px': gap, 'gap_m': gap / hm * 1.8, 'sigma_px': sigma, 'sigma_m': sigma / hm * 1.8})
    out.sort(key=lambda o: -o['gap_px'])
    return {'last': last, 'P': P, 'vp': vp, 'rows': out}


def status(row):
    """'off' beyond the line by more than the uncertainty, 'on' behind it by more, else 'close'."""
    if row['gap_px'] > row['sigma_px']: return 'off'
    if row['gap_px'] < -row['sigma_px']: return 'on'
    return 'close'


def draw(im, res, args, ball, cal=None, banner=True):
    W, H = im.shape[1], im.shape[0]
    pil = Image.fromarray(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)).convert('RGBA'); ov = Image.new('RGBA', pil.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    last = res['last']; best = res['rows'][0]; a = best['att']; st = status(best); P = res['P']; vp = res['vp']
    col = {'off': (255, 59, 48, 255), 'on': (52, 211, 110, 255), 'close': (255, 159, 10, 255)}[st]
    # the offside line: from the far touchline to the edge of the picture, through P and the vanishing point
    ta, tb = cal['touch'] if cal else (0.0, args.top)
    def xs_at(y): return line_x(P, vp, y)
    y_far = tb + ta * P[0]
    for _ in range(3): y_far = ta * xs_at(y_far) + tb  # the line meets the touchline where both agree
    y_end = H
    if vp and abs(xs_at(H) - P[0]) > 1e-6:
        edge = W - 1 if xs_at(H) > W - 1 else (0 if xs_at(H) < 0 else None)
        if edge is not None: y_end = P[1] + (edge - P[0]) / ((vp[0] - P[0]) / (vp[1] - P[1]))
    sg = best['sigma_px']
    d.polygon([(xs_at(y_far) - sg, y_far), (xs_at(y_far) + sg, y_far), (xs_at(y_end) + sg, y_end), (xs_at(y_end) - sg, y_end)], fill=col[:3] + (45,))  # uncertainty band
    d.line([(xs_at(y_far), y_far), (xs_at(y_end), y_end)], fill=(255, 255, 255, 90), width=14)
    d.line([(xs_at(y_far), y_far), (xs_at(y_end), y_end)], fill=(255, 255, 255, 255), width=4)
    d.line([(0, tb), (W, ta * W + tb)], fill=(90, 200, 255, 200), width=3)  # the far touchline
    if cal:  # the pitch lines the perspective comes from, where they are visible
        for l in cal['lines_used']:
            d.line([tuple(l['p0']), tuple(l['p1'])], fill=(90, 200, 255, 230), width=3)
        tag(d, (W - 560, 40), 'ligne médiane : sert à la perspective', (90, 200, 255, 255), 20, False)
    for p, c, lab in ((last, (255, 255, 255, 255), '2e dernier défenseur'), (a, col, 'attaquant le plus avancé')):
        b = p['box']; d.rectangle(b, outline=c, width=3); tag(d, (b[0], b[1] - 40), lab, c, 22)
    ax, ay = front(a['box'], args.attack), a['box'][3] + 14; lx = xs_at(a['box'][3])
    d.line([(lx, ay), (ax, ay)], fill=col, width=5)
    word = {'off': 'devant la ligne', 'on': 'derrière la ligne', 'close': 'de la ligne'}[st]
    tag(d, (min(ax, lx) + 10, ay + 10), f"{abs(best['gap_m']):.1f} m {word}  (± {best['sigma_m']:.1f} m)", col, 26)
    if ball is not None:
        bx, by = (ball['box'][0] + ball['box'][2]) / 2, (ball['box'][1] + ball['box'][3]) / 2
        d.ellipse([bx - 16, by - 16, bx + 16, by + 16], outline=(255, 214, 10, 255), width=3)
    if banner:
        txt = {'off': 'POSITION DE HORS-JEU', 'on': 'EN JEU', 'close': 'TROP JUSTE POUR TRANCHER'}[st]
        tag(d, (50, 40), txt, col, 44)
        tag(d, (50, 112), "Estimation indicative, une seule caméra : pas une décision officielle.", (255, 255, 255, 240), 22, False)
    return cv2.cvtColor(np.array(Image.alpha_composite(pil, ov).convert('RGB')), cv2.COLOR_RGB2BGR)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video'); ap.add_argument('out'); ap.add_argument('--pass-time', type=float, required=True)
    ap.add_argument('--attack', choices=['left', 'right'], required=True, help='the side the attacking team is going to')
    ap.add_argument('--crop', default='1920:1080:0:180', help='w:h:x:y of the match picture inside the recording')
    ap.add_argument('--red-hue', type=float, nargs=2, default=[0, 30]); ap.add_argument('--green-hue', type=float, nargs=2, default=[34, 95])
    ap.add_argument('--min-colour', type=float, default=0.35, help='min share of coloured torso pixels, below it the person is an official')
    ap.add_argument('--vp', type=float, nargs=2, help='vanishing point of the lines perpendicular to the touchlines, x y in the picture (else found from the pitch lines)')
    ap.add_argument('--aux-times', type=float, nargs='*', help='other moments of the clip that show pitch lines (default: pass time + 0.45 ... 1.25 s)')
    ap.add_argument('--top', type=int, default=190); ap.add_argument('--bottom', type=int, default=720)
    ap.add_argument('--hold', type=float, default=3.0, help='seconds of freeze frame'); ap.add_argument('--model', default=os.path.join(ROOT, 'models', 'yolox.onnx'))
    ap.add_argument('--json', help='also write the measurements here')
    a = ap.parse_args()
    det = Detector(a.model); im = grab(a.video, a.pass_time, a.crop); cal = None
    from calibrate import calibrate
    cal = calibrate(a.video, a.pass_time, a.crop, a.aux_times, top=a.top + 25)
    vp = tuple(a.vp) if a.vp else cal['vp']
    if vp: print(f"perspective: lines perpendicular to the touchlines meet at ({vp[0]:.0f}, {vp[1]:.0f}); from", [f"{l['angle']:.0f} deg line of {l['len']:.0f}px" for l in cal['lines_used']])
    else: print('WARNING: not enough pitch lines to find the perspective; the line is drawn vertical, which is only right near the middle of the picture.')
    players, balls = analyse(im, a, det); res = verdict(players, a.attack, vp)
    if not res: sys.exit('Could not find both attackers and defenders on that frame.')
    print('players:', [(p['team'], round(p['box'][0]), round(p['hue'])) for p in sorted(players, key=lambda p: p['box'][0])])
    for o in res['rows']: print(f"attacker at x={front(o['att']['box'], a.attack):.0f}: {o['gap_px']:+.0f}px = {o['gap_m']:+.2f} m (+- {o['sigma_m']:.2f} m) -> {status(o)}")
    frame = draw(im, res, a, pick_ball(balls, players), cal)
    png = os.path.splitext(a.out)[0] + '.png'; cv2.imwrite(png, frame); print('saved', png)
    if a.json: json.dump({'pass_time': a.pass_time, 'attack': a.attack, 'vp': vp, 'rows': [{'gap_px': float(o['gap_px']), 'gap_m': float(o['gap_m']), 'sigma_m': float(o['sigma_m']), 'status': status(o)} for o in res['rows']]}, open(a.json, 'w'), indent=1)
    # the video: the clip up to the pass, the freeze frame with the line, then the rest of the clip
    w, h = frame.shape[1], frame.shape[0]; fps = 30
    enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps), '-i', '-', '-c:v', 'libx264', '-crf', '18',
                            '-pix_fmt', 'yuv420p', '-movflags', '+faststart', a.out], stdin=subprocess.PIPE)
    cw, ch, cx, cy = [int(v) for v in a.crop.split(':')]
    rd = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', a.video, '-vf', f'crop={cw}:{ch}:{cx}:{cy},fps={fps}', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-'], stdout=subprocess.PIPE, bufsize=10 ** 8)
    i = 0; n_pass = int(round(a.pass_time * fps)); done = False
    while True:
        b = rd.stdout.read(w * h * 3)
        if len(b) < w * h * 3: break
        if i < n_pass: enc.stdin.write(b)
        else:
            if not done:
                for k in range(int(a.hold * fps)):  # the line grows from the top over a third of a second, then holds
                    prog = min(1.0, k / (0.35 * fps)); f = frame if prog >= 1 else cv2.addWeighted(im, 1 - prog, frame, prog, 0)
                    enc.stdin.write(f.tobytes())
                done = True
            enc.stdin.write(b)
        i += 1
    enc.stdin.close(); enc.wait(); print('Done:', a.out)


if __name__ == '__main__':
    main()
