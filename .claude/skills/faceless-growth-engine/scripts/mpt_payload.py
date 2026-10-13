#!/usr/bin/env python3
"""Construit le payload JSON d'une vidéo pour MoneyPrinterTurbo.

Usage :
    python3 mpt_payload.py script.json > payload.json

script.json :
    {
      "subject": "...",
      "script": "texte narré complet",
      "terms": ["keyword one", "keyword two"],
      "settings": {"voice_name": "...", "video_aspect": "9:16"}   (optionnel)
    }

Les noms de champs de l'API varient selon la version : vérifie la page /docs
de ton instance et ajuste FIELD_MAP si besoin avant d'automatiser.
"""
import json
import re
import sys

FIELD_MAP = {
    "subject": "video_subject",
    "script": "video_script",
    "terms": "video_terms",
}
DEFAULTS = {"video_aspect": "9:16"}
WORDS_MIN, WORDS_MAX = 80, 120  # ~30-45 s, à calibrer selon langue et voix


def clean_script(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]", "", text)  # retire les marqueurs [à vérifier]
    return re.sub(r"\s+", " ", text).strip()


def main(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for key in FIELD_MAP:
        if not data.get(key):
            print(f"Champ manquant : {key}", file=sys.stderr)
            return 1
    if "[à vérifier]" in data["script"]:
        print("Avertissement : le script contient encore [à vérifier].", file=sys.stderr)
    script = clean_script(data["script"])
    words = len(script.split())
    if not WORDS_MIN <= words <= WORDS_MAX:
        print(f"Avertissement : {words} mots (cible {WORDS_MIN}-{WORDS_MAX}).", file=sys.stderr)
    terms = data["terms"]
    payload = {
        FIELD_MAP["subject"]: data["subject"],
        FIELD_MAP["script"]: script,
        FIELD_MAP["terms"]: ", ".join(terms) if isinstance(terms, list) else terms,
        **DEFAULTS,
        **data.get("settings", {}),
    }
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
