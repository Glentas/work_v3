#!/usr/bin/env python3
"""Однократная установка модели spaCy en_core_web_sm (~12 Мб).

Модель та же, что в лр. №3 весеннего семестра: она даёт лемматизацию, теги
частей речи Penn Treebank, синтаксические роли и морфологические признаки,
на которых работают анализ и трансфер. После установки система работает
без доступа в интернет.

Скрипт работает в любом окружении:
* ``uv run python scripts/download_model.py``  (venv от uv — без pip);
* ``python scripts/download_model.py``         (обычный venv с pip).

Порядок попыток: ``uv pip install`` -> ``python -m pip install`` ->
ручная распаковка колеса (wheel — это zip-архив, pip не обязателен).

Использование:
    python scripts/download_model.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import sysconfig
import tempfile
import urllib.request
import zipfile
from pathlib import Path

MODEL = "en_core_web_sm"
VERSION = "3.7.1"
WHEEL_URL = (
    f"https://github.com/explosion/spacy-models/releases/download/"
    f"{MODEL}-{VERSION}/{MODEL}-{VERSION}-py3-none-any.whl"
)


def already_installed() -> bool:
    try:
        import spacy  # noqa: F401
        spacy.load(MODEL)
        return True
    except Exception:
        return False


def _try_uv() -> bool:
    """Установка через uv (venv проекта создается uv и не содержит pip)."""
    uv = shutil.which("uv")
    if uv is None:
        return False
    print("пробую uv pip install ...")
    result = subprocess.run(
        [uv, "pip", "install", "--python", sys.executable, WHEEL_URL],
        check=False,
    )
    return result.returncode == 0


def _try_pip() -> bool:
    """Установка через pip текущего интерпретатора (если он есть)."""
    probe = subprocess.run([sys.executable, "-m", "pip", "--version"],
                           check=False, capture_output=True)
    if probe.returncode != 0:
        return False
    print("пробую python -m pip install ...")
    result = subprocess.run([sys.executable, "-m", "pip", "install", WHEEL_URL],
                            check=False)
    return result.returncode == 0


def _manual_install() -> bool:
    """Без pip/uv: скачать колесо и распаковать его в site-packages.

    Wheel — обычный zip с каталогом пакета и метаданными dist-info, поэтому
    распаковка даёт полноценную установку.
    """
    target = Path(sysconfig.get_paths()["purelib"])
    print(f"pip/uv недоступны — распаковываю колесо вручную в {target}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            wheel = Path(tmp) / f"{MODEL}.whl"
            request = urllib.request.Request(
                WHEEL_URL, headers={"User-Agent": "lab4-translate/1.0"})
            print(f"скачиваю {WHEEL_URL} ...")
            with urllib.request.urlopen(request, timeout=600) as response:
                wheel.write_bytes(response.read())
            print(f"распаковываю ({wheel.stat().st_size / 1024 / 1024:.1f} Мб) ...")
            target.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(wheel) as archive:
                archive.extractall(target)
    except Exception as exc:  # сеть/права
        print(f"ручная установка не удалась: {exc}")
        return False
    return True


def main() -> None:
    if already_installed():
        print(f"модель уже установлена: {MODEL}")
        return

    installed = False
    for attempt in (_try_uv, _try_pip, _manual_install):
        if attempt() and already_installed():
            installed = True
            break

    if installed:
        print(f"готово: {MODEL} установлена")
        return

    print("не удалось установить модель автоматически.")
    print("Варианты ручной установки:")
    print(f"  uv pip install {WHEEL_URL}")
    print(f"  pip install {WHEEL_URL}")
    sys.exit(1)


if __name__ == "__main__":
    main()