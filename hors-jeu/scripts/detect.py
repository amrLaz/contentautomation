import cv2, numpy as np

class Detector:
    """YOLOX-S (COCO) through OpenCV's DNN, run over overlapping 640x640 tiles so small players are found."""
    def __init__(self, path):
        self.net = cv2.dnn.readNetFromONNX(path)
        hw = [(80, 8), (40, 16), (20, 32)]; g = []; s = []
        for n, st in hw:
            yy, xx = np.meshgrid(np.arange(n), np.arange(n), indexing='ij')
            g.append(np.stack([xx, yy], -1).reshape(-1, 2)); s.append(np.full((n * n, 1), st))
        self.grid = np.concatenate(g).astype(np.float32); self.stride = np.concatenate(s).astype(np.float32)

    def _tile(self, tile):
        blob = cv2.dnn.blobFromImage(tile, 1.0, (640, 640), swapRB=False)
        self.net.setInput(blob); out = self.net.forward()[0]
        xy = (out[:, :2] + self.grid) * self.stride; wh = np.exp(out[:, 2:4]) * self.stride
        sc = out[:, 4:5] * out[:, 5:]
        return xy, wh, sc

    def __call__(self, img, y0=0, y1=None, conf=0.35, size=640, step=480):
        H, W = img.shape[:2]; y1 = y1 or H; boxes, scores, classes = [], [], []
        ys = list(range(y0, max(y0 + 1, y1 - size + 1), step)) + [max(y0, y1 - size)]
        xs = list(range(0, max(1, W - size + 1), step)) + [max(0, W - size)]
        for ty in sorted(set(ys)):
            for tx in sorted(set(xs)):
                tile = img[ty:ty + size, tx:tx + size]
                if tile.shape[0] < size or tile.shape[1] < size:
                    pad = np.full((size, size, 3), 114, np.uint8); pad[:tile.shape[0], :tile.shape[1]] = tile; tile = pad
                xy, wh, sc = self._tile(tile)
                for c in (0, 32):  # person, sports ball
                    m = sc[:, c] > (conf if c == 0 else 0.15)
                    for (cx, cy), (w, h), s_ in zip(xy[m], wh[m], sc[m, c]):
                        boxes.append([cx - w / 2 + tx, cy - h / 2 + ty, w, h]); scores.append(float(s_)); classes.append(c)
        if not boxes: return []
        res = []
        for c in (0, 32):
            idx = [i for i, k in enumerate(classes) if k == c]
            if not idx: continue
            keep = cv2.dnn.NMSBoxes([boxes[i] for i in idx], [scores[i] for i in idx], 0.1, 0.45)
            for k in np.array(keep).reshape(-1): 
                i = idx[int(k)]; x, y, w, h = boxes[i]; res.append({'cls': 'person' if c == 0 else 'ball', 'box': (x, y, x + w, y + h), 'score': scores[i]})
        return res
