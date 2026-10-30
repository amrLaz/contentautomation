# hors-jeu (prototype)

Indicative offside check on a football clip: detects players, finds the second-last defender, draws the offside line on a
freeze frame at the pass and says whether the most advanced attacker is beyond it. Single camera: an estimate, never a decision.

    bash scripts/setup.sh
    .venv/bin/python scripts/offside.py clip.mp4 out.mp4 --pass-time 0.83 --attack left

## How it works
- `scripts/detect.py`: players and ball with YOLOX-S (COCO) through OpenCV DNN over overlapping 640x640 tiles (no PyTorch).
  Model from huggingface.co/opencv/object_detection_yolox (github.com/opencv/opencv_zoo/raw and download.pytorch.org are blocked by the cloud network policy).
- Teams from the hue of the torso. Officials are dropped (dark kit, few coloured pixels). Hue ranges are per match: the red kit
  reads 13-27 and the green 35-45 on the first test clip (`--red-hue`, `--green-hue`).
- The offside line is NOT vertical on screen. On a broadcast picture every line perpendicular to the touchlines meets at one point (a vanishing point)
  and leans more the further it is from that point. `scripts/calibrate.py` finds that point from white pitch lines parallel to the goal line (the goal line,
  the halfway line, box lines), even when they only show in other frames of the clip: the other frames are registered onto the pass frame (ORB features on the
  stands/boards, pan + zoom transform, the static logo ignored), lines are found with a top-hat filter + Hough (the lines are barely brighter than the grass in
  compressed video), merged, and a RANSAC picks the point at least two long lines point at. On the first clip: goal line (vertical, seen after the pan) and
  halfway line (16 deg) give (-181, -299), which agrees with the horizon read off the players' sizes (about -330).
- The line goes through the front-most body part of the second-last defender (the front-most visible defender when the keeper is out of frame) and the
  vanishing point, from the far touchline (bottom edge of the boards) to the edge of the picture. The gap is read at the attacker's own depth
  (a slanted line makes the depth matter: 10 px of height is about 19 px of gap here), in metres from the players' height (1.80 m).
- Uncertainty (pixels): reference point height 8 px x line slope, detection 8 px, vanishing point +-(60, 90) px, summed in quadrature. If the gap is
  smaller than that the verdict is "too close to call".

## Two modes
1. `scripts/offside.py` (vanishing point): needs two pitch lines parallel to the goal line; quick, rougher (+-0.6 m).
2. `scripts/offside_pitch.py` (metric pitch model): uses every marking visible in the clip. The best one.

### Pitch model (scripts/pitch_fit.py)
A homography from pitch metres (u along the pitch from the attacked goal line, v across from the far touchline) to the picture of the pass frame, fitted by robust least
squares on: the penalty-area front line (u=16.5), its near side line (v=54.16), the penalty arc, the halfway line (u=52.5), the centre circle, the foot of the boards
(a free offset, found to be 3 m outside the touchline), plus one radial lens term (k1=-0.012, almost nothing). Markings seen only in other frames are carried onto the pass
frame by the pan and zoom (ORB on the stands, similarity transform, the static logo ignored). The markings to use are listed per clip in `examples/clip2_pitch.json`
(regions to search + a first guess of a few pitch points); finding them automatically is not done.
Fit quality on the test clip: median error 8-16 cm per marking, and the model predicts the penalty-area corner within 10 px of where it was measured.
Independent check: the linesman, standing on the touchline, comes out at u=35.3 m and the second-last defender at 35.7 m, as the law asks of an assistant referee.
Sensitivity of the gap: dropping any marking except the penalty front line changes it by < 2 cm; carrying the other frames wrongly by 20 px changes it by < 4 cm;
the bootstrap over the marking pixels gives 0.3 cm. What dominates is where the two body parts are placed: +-2.5 px x, +-4 px y after zooming on them gives +-17 cm
(+-32 cm with the detector boxes alone, which also take in the arms).

### Test clip (69:05, HUSA in red attacking left against RCA in green), ball played at about 0.80-0.87 s
- Placement of the front-most legal body parts at ground level, after zooming (`--crops`): defender's boot (932,306); attacker's head/torso (1002,350), not his outstretched arm.
- Last source frame before the ball has moved (0.83 s): defender u = 35.68 m, attacker u = 35.66 m -> attacker +2 cm +- 17 cm (level).
- Next source frame, ball gone (0.87 s, carried onto the pass frame, camera had moved 11 px): attacker +35 cm +- 16 cm (ahead).
- The contact happened between the two source frames (the clip is a 60 fps screen recording of a source that changes every 3-4 frames), so the attacker was level to 35 cm ahead:
  TOO CLOSE TO CALL, leaning towards offside. The two earlier versions were wrong: a vertical line gave 1.5 m behind (onside), the vanishing-point line 0.3 +- 0.6 m.

## Limits and what is missing
- Pitch model: needs several markings (at least one long line parallel to the goal line plus another one or an arc and a circle); the landmark regions are drawn by hand per clip.
- The pass frame is given by hand (`--pass-time`). Detecting it from the ball trajectory is not done.
- The keeper is assumed to be the last defender and out of frame; the verdict is wrong if another defender is out of frame.
- Body parts: the box edge stands for the front-most body part; arms are not excluded.
- Camera pan/zoom between frames is not compensated (the analysis uses one frame).
- Not done: tracking over time, several attackers in one go with a verdict per player, a calibration with pitch lines (homography).
