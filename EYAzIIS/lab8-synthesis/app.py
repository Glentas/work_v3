"""Лабораторная работа 8. Автоматизированная система синтеза речи.

Вариант 7: немецкий язык, предметная область — «Сочинения по литературе».

Небольшое Flask-приложение (зависимости — uv). Доступны два движка синтеза:

1. Браузерный (Web Speech API, speechSynthesis) — работает в Chrome/Edge,
   использует голоса ОС; выполняется целиком на клиенте.
2. Серверный (espeak-ng) — надёжный запасной вариант для браузеров, где
   Web Speech API недоступен или не настроен (напр. Firefox/LibreWolf на Linux).
   Flask запускает espeak-ng, синтезирует WAV и отдаёт его клиенту.

Запуск:  uv run app.py   ->   http://127.0.0.1:5000
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
SAMPLES_FILE = BASE_DIR / "data" / "samples.json"

MAX_TEXT_LEN = 20000  # защита от чрезмерно длинных запросов

# Голоса серверного движка (варианты espeak-ng, mbrola не требуется).
SERVER_VOICES = [
    {"id": "de",        "label": "Стандартный (мужской)"},
    {"id": "de+f1",     "label": "Женский 1"},
    {"id": "de+f2",     "label": "Женский 2"},
    {"id": "de+f3",     "label": "Женский 3"},
    {"id": "de+f4",     "label": "Женский 4"},
    {"id": "de+m1",     "label": "Мужской 1"},
    {"id": "de+m3",     "label": "Мужской 3"},
    {"id": "de+m5",     "label": "Мужской 5"},
    {"id": "de+whisper", "label": "Шёпот"},
    {"id": "de+croak",  "label": "Хриплый"},
]
_ALLOWED_VOICES = {v["id"] for v in SERVER_VOICES}

app = Flask(__name__)


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _espeak_bin():
    """Возвращает путь к espeak-ng/espeak или None."""
    return shutil.which("espeak-ng") or shutil.which("espeak")


def load_samples():
    """Читает набор текстов предметной области из data/samples.json."""
    with SAMPLES_FILE.open(encoding="utf-8") as fh:
        return json.load(fh)


@app.route("/")
def index():
    """Главная страница системы синтеза."""
    return render_template("index.html")


@app.route("/api/samples")
def api_samples():
    """Готовые немецкие сочинения по литературе (JSON)."""
    return jsonify(load_samples())


@app.route("/api/server-voices")
def api_server_voices():
    """Список голосов серверного движка и признак его доступности."""
    return jsonify({"available": _espeak_bin() is not None, "voices": SERVER_VOICES})


@app.route("/api/tts", methods=["POST"])
def api_tts():
    """Серверный синтез: текст -> WAV (espeak-ng).

    Тело запроса (JSON): text, voice, rate, pitch.
    rate/pitch — относительные (как на клиенте, ~0.5..2.0).
    """
    espeak = _espeak_bin()
    if not espeak:
        return jsonify(error="espeak-ng не найден на сервере. Установите: sudo pacman -S espeak-ng"), 500

    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(error="Пустой текст"), 400
    if len(text) > MAX_TEXT_LEN:
        text = text[:MAX_TEXT_LEN]

    voice = data.get("voice") or "de"
    if voice not in _ALLOWED_VOICES:
        voice = "de"

    # Отображение клиентских диапазонов в параметры espeak-ng.
    rate = _clamp(int(round(_to_float(data.get("rate"), 1.0) * 175)), 80, 400)   # слов/мин
    pitch = _clamp(int(round(_to_float(data.get("pitch"), 1.0) * 50)), 0, 99)    # 0..99
    amp = 100  # громкость регулируется на клиенте (audio.volume)

    with tempfile.TemporaryDirectory() as d:
        infile = Path(d) / "in.txt"
        outfile = Path(d) / "out.wav"
        infile.write_text(text, encoding="utf-8")
        cmd = [espeak, "-v", voice, "-s", str(rate), "-p", str(pitch),
               "-a", str(amp), "-w", str(outfile), "-f", str(infile)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or b"").decode("utf-8", "ignore")
            return jsonify(error="Ошибка espeak-ng", detail=detail), 500
        except subprocess.TimeoutExpired:
            return jsonify(error="Слишком длинный текст (тайм-аут синтеза)"), 500
        wav = outfile.read_bytes()

    return Response(wav, mimetype="audio/wav",
                    headers={"Cache-Control": "no-store"})


def _to_float(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
