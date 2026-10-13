#!/usr/bin/env python3
"""Rend un quiz en Short vertical 1080x1920 (muet, lisible sans le son).

Usage :
    python3 tools/render_quiz.py quizzes/gevaudan.json out/gevaudan.mp4 [--frames-dir DIR] [--allow-unverified]

Un quiz contenant "[à vérifier]" est refusé tant que le fait n'est pas sourcé.

Spec JSON :
    {
      "hook": "texte d'accroche",
      "brand": "Quiz France",
      "questions": [
        {"level": 1, "question": "...", "options": ["A", "B"], "answer": 0,
         "answer_note": "phrase de réponse affichée"}
      ],
      "cta": "Ton score ? Dis-le en commentaire.",
      "sources": "optionnel, non affiché (traçabilité)"
    }

Timeline : accroche 3 s ; par question, 2 s de lecture + compte à rebours 3-2-1
puis 4 s de réponse ; CTA 3,5 s. Les fonds sont générés (pas de média tiers).
Nécessite Pillow et ffmpeg.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FPS = 30
LABELS = "ABCDEF"

PALETTE = {
    "bg_top": (18, 14, 38), "bg_bot": (52, 24, 70),
    "text": (245, 244, 250), "muted": (170, 165, 195),
    "accent": (255, 170, 60), "ok": (70, 200, 130), "box": (40, 34, 72),
}


def font(path, size):
    return ImageFont.truetype(path, size)


def background():
    img = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(img)
    t, b = PALETTE["bg_top"], PALETTE["bg_bot"]
    for y in range(H):
        k = y / (H - 1)
        px.line([(0, y), (W, y)], fill=tuple(int(t[i] + (b[i] - t[i]) * k) for i in range(3)))
    return img


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def text_block(draw, text, fnt, y, color, max_w=900, gap=1.25, center=True):
    for line in wrap(draw, text, fnt, max_w):
        w = draw.textlength(line, font=fnt)
        draw.text(((W - w) / 2 if center else 90, y), line, font=fnt, fill=color)
        y += int(fnt.size * gap)
    return y


def header(draw, brand, tag=None):
    draw.text((90, 110), brand.upper(), font=font(BOLD, 40), fill=PALETTE["accent"])
    if tag:
        f = font(BOLD, 40)
        draw.text((W - 90 - draw.textlength(tag, font=f), 110), tag, font=f, fill=PALETTE["muted"])


def card_hook(spec):
    img = background(); d = ImageDraw.Draw(img)
    header(d, spec["brand"])
    text_block(d, spec["hook"], font(BOLD, 84), 560, PALETTE["text"])
    return img


def card_question(spec, q, countdown=None):
    img = background(); d = ImageDraw.Draw(img)
    header(d, spec["brand"], f"NIVEAU {q['level']}")
    y = text_block(d, q["question"], font(BOLD, 70), 320, PALETTE["text"])
    y += 70
    fo = font(BOLD, 56)
    for i, opt in enumerate(q["options"]):
        d.rounded_rectangle([90, y, W - 90, y + 150], 36, fill=PALETTE["box"])
        d.text((140, y + 42), f"{LABELS[i]}", font=fo, fill=PALETTE["accent"])
        d.text((250, y + 42), opt, font=fo, fill=PALETTE["text"])
        y += 190
    if countdown:
        f = font(BOLD, 200)
        s = str(countdown)
        d.text(((W - d.textlength(s, font=f)) / 2, 1500), s, font=f, fill=PALETTE["accent"])
    return img


def card_answer(spec, q):
    img = background(); d = ImageDraw.Draw(img)
    header(d, spec["brand"], f"NIVEAU {q['level']}")
    y = text_block(d, q["question"], font(REG, 52), 280, PALETTE["muted"])
    y += 50
    fo = font(BOLD, 56)
    for i, opt in enumerate(q["options"]):
        good = i == q["answer"]
        d.rounded_rectangle([90, y, W - 90, y + 150], 36, fill=PALETTE["ok"] if good else PALETTE["box"])
        d.text((140, y + 42), LABELS[i], font=fo, fill=PALETTE["bg_top"] if good else PALETTE["muted"])
        d.text((250, y + 42), opt, font=fo, fill=PALETTE["bg_top"] if good else PALETTE["muted"])
        y += 190
    text_block(d, q["answer_note"], font(BOLD, 60), y + 60, PALETTE["text"])
    return img


def card_cta(spec):
    img = background(); d = ImageDraw.Draw(img)
    header(d, spec["brand"])
    text_block(d, spec["cta"], font(BOLD, 80), 640, PALETTE["text"])
    return img


def build_timeline(spec):
    tl = [(card_hook(spec), 3.0)]
    for q in spec["questions"]:
        tl.append((card_question(spec, q), 2.0))
        for c in (3, 2, 1):
            tl.append((card_question(spec, q, c), 1.0))
        tl.append((card_answer(spec, q), 4.0))
    tl.append((card_cta(spec), 3.5))
    return tl


def validate(spec, allow_unverified=False):
    if not allow_unverified and "[à vérifier]" in json.dumps(spec, ensure_ascii=False):
        sys.exit("Rendu refusé : le quiz contient encore [à vérifier] (porte Exactitude). "
                 "Sourcez le fait, ou utilisez --allow-unverified pour un essai interne.")
    probe = ImageDraw.Draw(Image.new("RGB", (W, H)))
    for key in ("hook", "brand", "questions", "cta"):
        if not spec.get(key):
            sys.exit(f"Champ manquant : {key}")
    for i, q in enumerate(spec["questions"], 1):
        for key in ("level", "question", "options", "answer", "answer_note"):
            if key not in q:
                sys.exit(f"Question {i} : champ manquant {key}")
        if not 0 <= q["answer"] < len(q["options"]):
            sys.exit(f"Question {i} : index de réponse invalide")
        if len(q["options"]) > 4:
            sys.exit(f"Question {i} : 4 options maximum")
        for opt in q["options"]:
            if probe.textlength(opt, font=font(BOLD, 56)) > W - 90 - 250 - 60:
                sys.exit(f"Question {i} : option trop longue ({opt!r}), à raccourcir")


def main(spec_path, out_path, frames_dir=None, allow_unverified=False):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    validate(spec, allow_unverified)
    out = Path(out_path); out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        fdir = Path(frames_dir or tmp); fdir.mkdir(parents=True, exist_ok=True)
        lines, total = [], 0.0
        for i, (img, dur) in enumerate(build_timeline(spec)):
            p = fdir / f"f{i:03d}.png"; img.save(p)
            lines += [f"file '{p.resolve()}'", f"duration {dur}"]
            total += dur
        lines.append(lines[-2])  # le concat demuxer ignore la durée de la dernière image
        lst = Path(tmp) / "list.txt"; lst.write_text("\n".join(lines), encoding="utf-8")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-movflags", "+faststart", str(out)],
            check=True)
    print(f"{out} : {total:.1f} s")


if __name__ == "__main__":
    allow = "--allow-unverified" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fd = sys.argv[sys.argv.index("--frames-dir") + 1] if "--frames-dir" in sys.argv else None
    if fd in args:
        args.remove(fd)
    if len(args) != 2:
        print(__doc__, file=sys.stderr); sys.exit(2)
    main(args[0], args[1], fd, allow)
