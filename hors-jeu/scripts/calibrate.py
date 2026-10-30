#!/usr/bin/env python3
"""Find where the lines perpendicular to the touchlines meet (their vanishing point) in the frame of the pass.

On a broadcast picture the offside line is NOT vertical: every line parallel to the goal line converges to one point, and the line
leans more the further it is from that point. The point is found from the white pitch lines that are parallel to the goal line
(the goal line itself, the halfway line, the box lines), even when they are only visible in other frames of the clip:
  1. the other frames are registered onto the frame of the pass (ORB features on the stands and boards + a homography, which is exact for a camera that only pans),
  2. long white straight lines are detected in every frame (top-hat filter + Hough) and carried over to the pass frame,
  3. duplicates are merged, lines along the touchlines (nearly horizontal) are dropped,
  4. a RANSAC finds the point most lines point at. Needs at least two different lines.
"""
import math, subprocess, sys
import numpy as np, cv2


def grab_frames(video, times, crop):
    w, h, x, y = [int(v) for v in crop.split(':')]; out = {}
    for t in times:
        p = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t:.3f}', '-i', video, '-frames:v', '1', '-vf', f'crop={w}:{h}:{x}:{y}', '-f', 'image2pipe', '-vcodec', 'png', '-'],
                           capture_output=True, check=True).stdout
        out[t] = cv2.imdecode(np.frombuffer(p, np.uint8), 1)
    return out


def register(frames, t0, stand_rows=(0, 250)):
    """Transform of every frame onto frame t0, as a 3x3 matrix. The camera pans and zooms, so a shift + uniform scale + small rotation
    (4 degrees of freedom) is used: a full homography fitted on the thin strip of stands extrapolates badly to the pitch."""
    def feats(im):
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY); m = np.zeros(g.shape, np.uint8); m[stand_rows[0]:stand_rows[1], :] = 255
        return cv2.ORB_create(4000).detectAndCompute(g, m)
    k0, d0 = feats(frames[t0]); bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True); Hs = {t0: np.eye(3)}
    for t, im in frames.items():
        if t == t0: continue
        k, d = feats(im)
        if d is None or d0 is None: continue
        ms = sorted(bf.match(d, d0), key=lambda m: m.distance)[:900]
        src = np.float32([k[m.queryIdx].pt for m in ms]); dst = np.float32([k0[m.trainIdx].pt for m in ms]); disp = np.hypot(*(dst - src).T)
        if len(ms) and np.median(disp[disp > 2]) > 5 if (disp > 2).any() else False:  # the camera moved: points that stay put are overlays (logo, scoreboard)
            keep = disp > 2; src, dst = src[keep], dst[keep]
        if len(src) < 40: continue
        A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
        if A is not None and inl.sum() >= 40: Hs[t] = np.vstack([A, [0, 0, 1]])
    return Hs


def detect_lines(im, top=215, min_len=140, contrast=13):
    """Long straight white lines on the grass. The top-hat filter keeps what is brighter than its surroundings, which works on compressed video where the lines are barely whiter than the grass."""
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    th = cv2.morphologyEx(g, cv2.MORPH_TOPHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21)))
    m = (th > contrast).astype(np.uint8) * 255; m[:top, :] = 0
    L = cv2.HoughLinesP(m, 1, np.pi / 720, threshold=60, minLineLength=min_len, maxLineGap=14)
    return [] if L is None else np.array(L).reshape(-1, 4).astype(float)


def normal_form(p):
    x0, y0, x1, y1 = p; a = math.atan2(y1 - y0, x1 - x0) % math.pi
    n = (-math.sin(a), math.cos(a)); rho = x0 * n[0] + y0 * n[1]
    return a, rho


def merge(lines, ang_tol=math.radians(1.5), rho_tol=14):
    """Merge near-identical lines (same line seen in several frames or detected twice); weight = length covered."""
    groups = []
    for p in lines:
        a, rho = normal_form(p)
        for g in groups:
            da = abs((a - g['a'] + math.pi / 2) % math.pi - math.pi / 2)
            if da < ang_tol and abs(rho - g['rho']) < rho_tol:
                g['pts'] += [p[:2], p[2:]]; break
        else: groups.append({'a': a, 'rho': rho, 'pts': [p[:2], p[2:]]})
    out = []
    for g in groups:
        pts = np.array(g['pts']); vx, vy, cx, cy = cv2.fitLine(pts.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        proj = (pts[:, 0] - cx) * vx + (pts[:, 1] - cy) * vy
        out.append({'p0': (cx + vx * proj.min(), cy + vy * proj.min()), 'p1': (cx + vx * proj.max(), cy + vy * proj.max()), 'len': float(proj.max() - proj.min()),
                    'angle': math.degrees(math.atan2(vy, vx)) % 180})
    return out


def vanishing_point(lines, min_len=250, max_touch_angle=7, tol_deg=0.8):
    """The point that most long lines point at, among lines that are not along the touchlines. -> (x, y, supporting lines) or None."""
    cand = [l for l in lines if l['len'] >= min_len and min(l['angle'], 180 - l['angle']) > max_touch_angle]
    best = None
    for i in range(len(cand)):
        for j in range(i + 1, len(cand)):
            a, b = cand[i], cand[j]
            if abs((a['angle'] - b['angle'] + 90) % 180 - 90) < 4: continue
            p = intersect(a, b)
            if p is None: continue
            sup = [l for l in cand if angular_residual(l, p) < tol_deg]
            score = sum(l['len'] for l in sup)
            if len(sup) >= 2 and (best is None or score > best[0]): best = (score, p, sup)
    return None if best is None else (best[1][0], best[1][1], best[2])


def intersect(a, b):
    x1, y1 = a['p0']; x2, y2 = a['p1']; x3, y3 = b['p0']; x4, y4 = b['p1']
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-9: return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
    return x1 + t * (x2 - x1), y1 + t * (y2 - y1)


def angular_residual(l, p):
    """Angle (deg) between the line and the direction from the line's middle to the point."""
    mx, my = (l['p0'][0] + l['p1'][0]) / 2, (l['p0'][1] + l['p1'][1]) / 2
    a1 = math.atan2(l['p1'][1] - l['p0'][1], l['p1'][0] - l['p0'][0]); a2 = math.atan2(p[1] - my, p[0] - mx)
    return abs(math.degrees((a1 - a2 + math.pi / 2) % math.pi - math.pi / 2))


def far_touchline(im, y_range=(100, 260)):
    """The far touchline as the bottom edge of the advertising boards: y = a*x + b, fitted on the strongest white-to-dark step of each column, outliers dropped."""
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY).astype(float); xs, ys = [], []
    for x in range(40, g.shape[1] - 40, 40):
        col = g[y_range[0]:y_range[1], x - 6:x + 7].mean(1); xs.append(x); ys.append(y_range[0] + int(np.argmin(np.diff(col))))
    xs, ys = np.array(xs, float), np.array(ys, float); keep = np.ones(len(xs), bool)
    for _ in range(4):
        a, b = np.polyfit(xs[keep], ys[keep], 1); keep = np.abs(ys - (a * xs + b)) < 5
        if keep.sum() < 8: break
    return float(a), float(b)


def calibrate(video, t_pass, crop='1920:1080:0:180', aux=None, top=215):
    aux = aux if aux is not None else [t_pass + d for d in (0.0, 0.45, 0.65, 0.85, 1.05, 1.25)]
    times = sorted(set([round(t_pass, 3)] + [round(t, 3) for t in aux])); frames = grab_frames(video, times, crop)
    t0 = round(t_pass, 3); Hs = register(frames, t0); allL = []
    for t, im in frames.items():
        if t not in Hs: continue
        for l in detect_lines(im, top):
            q = cv2.perspectiveTransform(np.float32(l.reshape(-1, 1, 2)), Hs[t]).reshape(-1)
            allL.append(q)
    merged = merge(allL); vp = vanishing_point(merged)
    return {'touch': far_touchline(frames[t0]), 'vp': None if vp is None else (float(vp[0]), float(vp[1])), 'lines_used': [] if vp is None else vp[2], 'all_lines': merged, 'frames_used': sorted(Hs), 'frame': frames[t0]}


if __name__ == '__main__':
    r = calibrate(sys.argv[1], float(sys.argv[2]))
    print('frames used', r['frames_used']); print('vanishing point', r['vp'])
    for l in r['lines_used']: print('  line', [round(v) for v in l['p0']], [round(v) for v in l['p1']], 'len', round(l['len']), 'angle', round(l['angle'], 1))
