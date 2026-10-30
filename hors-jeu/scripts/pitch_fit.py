#!/usr/bin/env python3
"""Fit a model of the pitch to every marking visible in a clip: a homography from pitch metres to the picture of the pass frame.

Markings used (FIFA pitch, 105 x 68 m; u runs along the pitch from the goal line the team attacks, v across from the far touchline):
  penalty-area front line (u = 16.5), its near side line (v = 54.16), the penalty arc (circle of 9.15 m around the mark at u = 11),
  the halfway line (u = 52.5), the centre circle (9.15 m around (52.5, 34)), and the far touchline (the foot of the boards, a few metres outside).
Markings that only show in other frames are carried onto the pass frame by the camera's pan and zoom (calibrate.register).
The fit also estimates a little lens distortion (one radial term): the markings are straight lines and circles on a flat pitch, so the right amount
of distortion is the one that makes them agree.

This file holds the landmark regions of ONE clip (the RCA-HUSA test clip) as LANDMARKS: they have to be redrawn for another clip, until the markings are found automatically.
"""
import json, math, os, sys
import numpy as np, cv2
from scipy.optimize import least_squares

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calibrate import grab_frames, register

C0 = np.array([960.0, 540.0])   # picture centre = principal point
PEN_FRONT, PEN_SIDE, PEN_MARK, R_CIRCLE, HALF = 16.5, 54.16, 11.0, 9.15, 52.5
MID_V = 34.0

# regions (in pass-frame pixels) where each marking is searched, and in which frames; clip-specific
LANDMARKS = {
    'front': {'poly': [(-235, 300), (-85, 300), (-85, 735), (-235, 735)], 'frames': 'later', 'thr': 25},
    'side':  {'poly': [(-700, 738), (-195, 738), (-195, 800), (-700, 800)], 'frames': 'later', 'thr': 25},
    'arc':   {'poly': [(-85, 380), (140, 380), (140, 575), (-85, 575)], 'frames': 'later', 'thr': 18},
    'half':  {'poly': [(1570, 178), (1850, 258), (1850, 292), (1570, 212)], 'frames': 'pass', 'thr': 22},
    'circle': {'poly': [(1590, 316), (1800, 346), (1919, 340), (1919, 505), (1590, 505)], 'frames': 'pass', 'thr': 22},
}


def tophat(im):
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    return cv2.morphologyEx(g, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21)))


def undistort(p, k1):
    """p: (N,2) picture points -> same points with the radial distortion removed."""
    d = p - C0; r2 = (d ** 2).sum(1, keepdims=True) / 1000.0 ** 2
    return C0 + d * (1 + k1 * r2)


def extract(frames, Hs, t_pass, landmarks=LANDMARKS, step=3):
    """-> {name: [(points in the frame's own pixels, 3x3 matrix frame -> pass frame), ...]}"""
    out = {k: [] for k in landmarks}; th = {t: tophat(im) for t, im in frames.items()}
    for name, lm in landmarks.items():
        ts = [t for t in frames if t != t_pass and t in Hs] if lm['frames'] == 'later' else [t_pass]
        for t in ts:
            A = Hs[t]; Ainv = np.linalg.inv(A)
            poly = cv2.perspectiveTransform(np.float32(lm['poly']).reshape(-1, 1, 2), Ainv).reshape(-1, 2).astype(np.int32)
            m = np.zeros(th[t].shape, np.uint8); cv2.fillPoly(m, [poly], 255)
            ys, xs = np.where((th[t] > lm['thr']) & (m > 0))
            if len(xs) == 0: continue
            pts = np.stack([xs, ys], 1).astype(float)[::step]
            out[name].append((pts, A))
    return out


def far_touchline_points(im, x_range=(150, 1150)):
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(float); xs, ys = [], []
    for x in range(x_range[0], x_range[1], 25):
        col = g[100:260, x - 6:x + 7].mean(1); xs.append(x); ys.append(100 + int(np.argmin(np.diff(col))))
    xs, ys = np.array(xs, float), np.array(ys, float); keep = np.ones(len(xs), bool)
    for _ in range(4):
        a, b = np.polyfit(xs[keep], ys[keep], 1); keep = np.abs(ys - (a * xs + b)) < 4
    return np.stack([xs[keep], ys[keep]], 1)


def to_pass(pts, A, k1):
    """Points of a frame -> undistorted points of the pass frame."""
    u = undistort(pts, k1); h = np.hstack([u, np.ones((len(u), 1))]) @ A.T
    return h[:, :2] / h[:, 2:3]


def pitch_of(Hn, p):
    """Undistorted pass-frame pixels -> pitch metres (u, v). Hn maps (u/10, v/10, 1) to pixels/1000."""
    q = np.hstack([p / 1000.0, np.ones((len(p), 1))]) @ np.linalg.inv(Hn).T
    return 10 * q[:, :2] / q[:, 2:3]


def residuals(theta, meas, far, fit_k1=True):
    Hn = np.append(theta[:8], 1.0).reshape(3, 3); k1 = theta[8] if fit_k1 else 0.0; dfar = theta[9]
    res = []
    for name, items in meas.items():
        for pts, A in items:
            uv = pitch_of(Hn, to_pass(pts, A, k1)); u, v = uv[:, 0], uv[:, 1]
            if name == 'front': r = u - PEN_FRONT
            elif name == 'side': r = v - PEN_SIDE
            elif name == 'half': r = u - HALF
            elif name == 'arc': r = np.hypot(u - PEN_MARK, v - MID_V) - R_CIRCLE
            elif name == 'circle': r = np.hypot(u - HALF, v - MID_V) - R_CIRCLE
            res.append(r / 0.25)
    uv = pitch_of(Hn, undistort(far, k1)); res.append((uv[:, 1] + dfar) / 0.25)   # the boards stand dfar metres outside the touchline
    return np.concatenate(res)


DEFAULT_INIT = {'pitch': [[16.5, 54.16], [16.5, 13.84], [16.5, 26.69], [16.5, 41.31], [20.15, 34.0], [52.5, 24.85], [43.35, 34.0]],
                'image': [[-160, 755], [-160, 287], [-160, 395], [-160, 555], [95, 450], [1830, 272], [1615, 385]]}


def load_cfg(path):
    """A clip's configuration: {'later': [times], 'landmarks': {name: {poly, frames, thr}}, 'init': {'pitch': [...], 'image': [...]}}."""
    return json.load(open(path))


def initial_homography(init=None):
    """A first guess from a handful of pitch points read off the picture (pass-frame pixels); the fit then refines it."""
    init = init or DEFAULT_INIT
    H, _ = cv2.findHomography(np.float32(init['pitch']) / 10.0, np.float32(init['image']) / 1000.0, 0)
    return H / H[2, 2]


def fit(video, t_pass, crop='1920:1080:0:180', cfg=None, verbose=True):
    cfg = cfg or {}; later = cfg.get('later', (1.28, 1.48, 1.68, 1.88, 2.08)); landmarks = cfg.get('landmarks', LANDMARKS)
    times = sorted(set([round(t_pass, 3)] + [round(t, 3) for t in later])); frames = grab_frames(video, times, crop)
    t0 = round(t_pass, 3); Hs = register(frames, t0); meas = extract(frames, Hs, t0, landmarks); far = far_touchline_points(frames[t0])
    H0 = initial_homography(cfg.get('init')); theta0 = np.concatenate([H0.ravel()[:8], [0.0, 2.0]])
    for stage, fit_k1 in (('no lens distortion', False), ('with lens distortion', True)):
        lb = np.full(10, -np.inf); ub = np.full(10, np.inf)
        if not fit_k1: lb[8], ub[8] = -1e-9, 1e-9
        r = least_squares(residuals, theta0, args=(meas, far, fit_k1), loss='soft_l1', f_scale=1.5, bounds=(lb, ub)); theta0 = r.x
        if verbose:
            n = {k: sum(len(p) for p, _ in v) for k, v in meas.items()}
            print(f'[{stage}] points {n}, far {len(far)}; robust RMS {np.sqrt(np.mean(r.fun ** 2)) * 0.25:.3f} m; k1={r.x[8]:+.4f}; boards {r.x[9]:.1f} m outside the touchline')
            Hn = np.append(r.x[:8], 1.0).reshape(3, 3); k1 = r.x[8]; i = 0
            for name, items in meas.items():
                rr = np.concatenate([residuals_class(name, Hn, k1, p, A) for p, A in items]) if items else np.array([0.0])
                print(f'    {name:7s} median |error| {np.median(np.abs(rr)):.2f} m, 90% {np.percentile(np.abs(rr), 90):.2f} m')
    Hn = np.append(r.x[:8], 1.0).reshape(3, 3)
    return {'Hn': Hn, 'k1': float(r.x[8]), 'board_offset': float(r.x[9]), 'meas': meas, 'far': far, 'frame': frames[t0], 'theta': r.x, 'Hs': Hs, 'times': times}


def residuals_class(name, Hn, k1, pts, A):
    uv = pitch_of(Hn, to_pass(pts, A, k1)); u, v = uv[:, 0], uv[:, 1]
    if name == 'front': return u - PEN_FRONT
    if name == 'side': return v - PEN_SIDE
    if name == 'half': return u - HALF
    if name == 'arc': return np.hypot(u - PEN_MARK, v - MID_V) - R_CIRCLE
    return np.hypot(u - HALF, v - MID_V) - R_CIRCLE


def image_of(Hn, k1, uv):
    """Pitch metres -> picture pixels (distortion put back, by a few fixed-point steps)."""
    uv = np.asarray(uv, float).reshape(-1, 2); q = np.hstack([uv / 10.0, np.ones((len(uv), 1))]) @ Hn.T
    p = 1000.0 * q[:, :2] / q[:, 2:3]; d = p.copy()
    for _ in range(6):  # invert undistort(): find the distorted point whose undistorted version is p
        d = C0 + (p - C0) / (1 + k1 * ((d - C0) ** 2).sum(1, keepdims=True) / 1000.0 ** 2)
    return d


def locate(r, pts):
    """Picture pixels (N,2) of the pass frame -> pitch metres (N,2)."""
    return pitch_of(r['Hn'], undistort(np.asarray(pts, float).reshape(-1, 2), r['k1']))


def pitch_curves(r, n=60):
    """The pitch markings re-drawn from the fitted model, as pixel polylines: {name: (N,2)}. Used to show how well the model fits."""
    L, Wd = 105.0, 68.0; cv = {}
    def seg(name, a, b): cv[name] = image_of(r['Hn'], r['k1'], np.linspace(a, b, n))
    seg('far touchline', (0, 0), (L, 0)); seg('near touchline', (0, Wd), (L, Wd)); seg('goal line', (0, 0), (0, Wd)); seg('halfway', (HALF, 0), (HALF, Wd))
    seg('pen front', (PEN_FRONT, 13.84), (PEN_FRONT, 54.16)); seg('pen far side', (0, 13.84), (PEN_FRONT, 13.84)); seg('pen near side', (0, 54.16), (PEN_FRONT, 54.16))
    seg('goal area front', (5.5, 24.84), (5.5, 43.16)); seg('goal area far side', (0, 24.84), (5.5, 24.84)); seg('goal area near side', (0, 43.16), (5.5, 43.16))
    a = math.acos((PEN_FRONT - PEN_MARK) / R_CIRCLE); th = np.linspace(-a, a, n)
    cv['penalty arc'] = image_of(r['Hn'], r['k1'], np.stack([PEN_MARK + R_CIRCLE * np.cos(th), MID_V + R_CIRCLE * np.sin(th)], 1))
    th = np.linspace(0, 2 * math.pi, 2 * n); cv['centre circle'] = image_of(r['Hn'], r['k1'], np.stack([HALF + R_CIRCLE * np.cos(th), MID_V + R_CIRCLE * np.sin(th)], 1))
    return cv


if __name__ == '__main__':
    r = fit(sys.argv[1], float(sys.argv[2]))
    Hn, k1 = r['Hn'], r['k1']
    for lab, uv in (('penalty corner near', (16.5, 54.16)), ('penalty corner far', (16.5, 13.84)), ('halfway x far touchline', (52.5, -r['board_offset'])), ('centre spot', (52.5, 34.0))):
        print(f'  {lab:28s} -> pixel {image_of(Hn, k1, uv).round(0).tolist()}')
