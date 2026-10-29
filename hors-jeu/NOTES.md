# hors-jeu (prototype, not a skill yet)

Goal: detect an offside position on a football clip and draw the line.

## Done
- `scripts/detect.py`: players and ball with YOLOX-S (COCO) run through OpenCV DNN over overlapping 640x640 tiles
  (no PyTorch needed). Model: `object_detection_yolox_2022nov.onnx` from huggingface.co/opencv/object_detection_yolox
  (github.com/opencv/opencv_zoo/raw is blocked by the cloud network policy, huggingface.co works; download.pytorch.org is blocked).
- `scripts/scan.py`: runs the detector on frames of a clip and tiles them, boxes coloured by team (jersey hue).
  The team colour ranges are tuned for red (hue <19 or >165), green (38-95), keeper yellow (19-38): retune per match.

## Findings on the first clip (screen recording of a highlights reel, RCA vs HUSA, 68:57-69:01)
- The video area is a 1920x1080 window at y=180 inside a 1920x1440 screen recording; the rest is player UI and subtitles.
- The action starts at 4.05 s, right after a cut: the ball is already played, so the pass frame is NOT in the clip.
- Few pitch lines are visible in the key frames, so the goal-line vanishing point cannot be estimated reliably yet.

## Missing
- the moment of the pass, pitch geometry (vanishing point / homography per frame), body-part selection, the drawn line, the verdict with its margin.
