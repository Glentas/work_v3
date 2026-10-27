"""Распознавание речи через Vosk (офлайн).

Модели лежат в каталоге models/ (см. scripts/download_model.py).
Работает без интернета; не зависит от браузерного Web Speech API, поэтому
пригодно для Firefox/LibreWolf.
"""
import io
import json
import os
import wave

from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(-1)  # тише логи Vosk/Kaldi

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

# Язык -> каталог модели (малые модели Vosk).
MODEL_DIRS = {
    "de": "vosk-model-small-de-0.15",
    "en": "vosk-model-small-en-us-0.15",
    "ru": "vosk-model-small-ru-0.22",
}

LANG_NAMES = {"de": "Немецкий", "en": "Английский", "ru": "Русский"}

_cache = {}  # lang -> Model


def model_path(lang):
    d = MODEL_DIRS.get(lang)
    return os.path.join(MODELS_DIR, d) if d else None


def is_available(lang):
    p = model_path(lang)
    return bool(p) and os.path.isdir(p)


def available_languages():
    return [lang for lang in MODEL_DIRS if is_available(lang)]


def get_model(lang):
    """Загружает (и кэширует) модель для языка."""
    if lang in _cache:
        return _cache[lang]
    path = model_path(lang)
    if not path or not os.path.isdir(path):
        raise FileNotFoundError(
            f"Модель для '{lang}' не найдена. Запустите: "
            f"uv run python scripts/download_model.py {lang}"
        )
    _cache[lang] = Model(path)
    return _cache[lang]


def recognize_wav(wav_bytes, lang):
    """Распознаёт PCM/WAV-байты и возвращает текст (строка)."""
    model = get_model(lang)
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        rate = wf.getframerate()
        rec = KaldiRecognizer(model, rate)
        rec.SetWords(False)
        text_parts = []
        while True:
            frames = wf.readframes(4000)
            if not frames:
                break
            if rec.AcceptWaveform(frames):
                part = json.loads(rec.Result()).get("text", "")
                if part:
                    text_parts.append(part)
        final = json.loads(rec.FinalResult()).get("text", "")
        if final:
            text_parts.append(final)
    return " ".join(text_parts).strip()
