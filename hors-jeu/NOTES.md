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
- The line goes through the front-most body part of the second-last defender (the front-most visible defender when the keeper is out of frame),
  in the direction of the goal line (`--line-angle`, 0 = vertical on screen; measured 0 to 0.3 degrees on the first clip with a Hough transform
  after a top-hat filter, because the white lines are barely brighter than the grass in compressed video).
- Distance in metres from the players' own height (1.80 m), so it is rough (about +-0.5 m).

## First test (clip 2, 69:05, HUSA in red attacking left against RCA in green)
- Ball leaves the red player on the right at about 0.83 s (the ball is detected at rest at (1111,269) until then; the clip is a screen recording
  at 60 fps of a source that repeats each frame, so positions only change every 2-4 frames).
- The most advanced attacker is 73 px (about 1.5 m) behind the second-last defender: ON SIDE. The linesman at the touchline was first
  mistaken for an attacker (orange flag), and is now excluded by the colour-share rule.

## Limits and what is missing
- Perspective: the line direction is taken as the goal line's on-screen direction; lines parallel to it converge towards a vanishing point,
  so a long line drifts by a few degrees. Fine for short distances, wrong for a line drawn across the whole pitch.
- The pass frame is given by hand (`--pass-time`). Detecting it from the ball trajectory is not done.
- The keeper is assumed to be the last defender and out of frame; the verdict is wrong if another defender is out of frame.
- Body parts: the box edge stands for the front-most body part; arms are not excluded.
- Camera pan/zoom between frames is not compensated (the analysis uses one frame).
- Not done: tracking over time, several attackers in one go with a verdict per player, a calibration with pitch lines (homography).
