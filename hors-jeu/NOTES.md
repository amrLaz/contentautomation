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

## First test (clip 2, 69:05, HUSA in red attacking left against RCA in green)
- Ball leaves the red player on the right at about 0.83 s (detected at rest at (1111,269) until then; the clip is a 60 fps screen recording of a source
  that repeats frames, so positions only change every 2-4 frames).
- With a vertical line (my first version, wrong) the most advanced attacker was 1.5 m behind the line: "on side".
  With the line perpendicular to the touchlines it is 0.3 m beyond it +- 0.6 m: TOO CLOSE TO CALL. The perspective changed the answer.
- The linesman at the touchline was first mistaken for an attacker (orange flag); dropped by the colour-share rule.

## Limits and what is missing
- Perspective: needs at least two different pitch lines parallel to the goal line somewhere in the clip; without them the line falls back to vertical and a warning is printed.
  Lens distortion is ignored (the far touchline bends by about 1 degree across the picture).
- The pass frame is given by hand (`--pass-time`). Detecting it from the ball trajectory is not done.
- The keeper is assumed to be the last defender and out of frame; the verdict is wrong if another defender is out of frame.
- Body parts: the box edge stands for the front-most body part; arms are not excluded.
- Camera pan/zoom between frames is not compensated (the analysis uses one frame).
- Not done: tracking over time, several attackers in one go with a verdict per player, a calibration with pitch lines (homography).
