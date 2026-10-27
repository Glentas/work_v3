"""Одноразовая загрузка модели Vosk для распознавания.

Использование:
    uv run python scripts/download_model.py de     # немецкий (вариант 7)
    uv run python scripts/download_model.py en     # английский
    uv run python scripts/download_model.py ru     # русский

Модель распаковывается в каталог models/ рядом с приложением.
"""
import os
import sys
import urllib.request
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE, "models")

MODELS = {
    "de": ("vosk-model-small-de-0.15",
           "https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip"),
    "en": ("vosk-model-small-en-us-0.15",
           "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"),
    "ru": ("vosk-model-small-ru-0.22",
           "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"),
}


def _progress(done, total):
    if total > 0:
        pct = min(100, done * 100 // total)
        sys.stdout.write(f"\r  {pct:3d}%  ({done // 1048576}/{total // 1048576} Мб)")
        sys.stdout.flush()


def download(lang):
    if lang not in MODELS:
        sys.exit(f"Неизвестный язык '{lang}'. Доступны: {', '.join(MODELS)}")
    name, url = MODELS[lang]
    dest = os.path.join(MODELS_DIR, name)
    if os.path.isdir(dest):
        print(f"Модель уже установлена: {dest}")
        return
    os.makedirs(MODELS_DIR, exist_ok=True)
    zpath = os.path.join(MODELS_DIR, name + ".zip")

    print(f"Скачиваю модель '{lang}': {url}")
    last = {"n": 0}

    def hook(n, bs, total):
        done = n * bs
        if done - last["n"] >= 1048576 or (total > 0 and done >= total):
            last["n"] = done
            _progress(done, total)

    urllib.request.urlretrieve(url, zpath, hook)
    print("\nРаспаковываю…")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(MODELS_DIR)
    os.remove(zpath)
    print(f"Готово: {dest}")


if __name__ == "__main__":
    download(sys.argv[1] if len(sys.argv) > 1 else "de")
