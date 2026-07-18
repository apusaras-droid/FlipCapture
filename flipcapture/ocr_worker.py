from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image

from .ocr import recognize_text


def main() -> int:
    if len(sys.argv) != 4:
        return 2
    with Image.open(Path(sys.argv[1])) as image:
        text = recognize_text(image, quality_mode=sys.argv[3])
    Path(sys.argv[2]).write_text(json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
