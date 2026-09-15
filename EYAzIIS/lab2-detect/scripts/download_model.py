#!/usr/bin/env python3
"""Однократное скачивание нейросетевой модели fastText lid.176.ftz (916 Кб).

Модель кладётся в models/ и коммитится в репозиторий: дальше система
распознаёт текст без доступа в интернет. Лицензия модели — CC-BY-SA 3.0
(обучена на данных Wikipedia + Tatoeba + SETimes под той же лицензией).

Использование:
    python scripts/download_model.py
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET = PROJECT_ROOT / "models" / "lid.176.ftz"
URL = "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"


def main() -> None:
    if TARGET.exists():
        print(f"модель уже на месте: {TARGET} ({TARGET.stat().st_size / 1024:.0f} Кб)")
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    print(f"скачиваю {URL} ...")
    request = urllib.request.Request(URL, headers={"User-Agent": "lab2-detect/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response:
        data = response.read()
    TARGET.write_bytes(data)
    print(f"готово: {TARGET} ({len(data) / 1024:.0f} Кб)")


if __name__ == "__main__":
    main()
