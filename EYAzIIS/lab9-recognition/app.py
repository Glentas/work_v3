"""Лабораторная работа 9. Автоматизированная система распознавания речи.

Вариант 7: немецкий язык, предметная область — «Сочинения по литературе».

Небольшое Flask-приложение (зависимости — uv). Браузер записывает речь с
микрофона и присылает WAV; сервер распознаёт её офлайн через Vosk, сопоставляет
фразу со списком операций и возвращает команду, которую клиент автоматически
исполняет с уведомлением пользователя.

Запуск:  uv run app.py   ->   http://127.0.0.1:5000
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

import commands as cmd
import recognizer

app = Flask(__name__)

DEFAULT_LANG = "de"  # язык по умолчанию — вариант 7 (немецкий)
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # ~25 Мб на запись
MAX_TTS_LEN = 20000  # ограничение длины текста для синтеза


def _espeak_bin():
    return shutil.which("espeak-ng") or shutil.which("espeak")


def _to_float(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default



@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config")
def api_config():
    """Доступные языки (у которых скачана модель) и язык по умолчанию."""
    langs = []
    for code in recognizer.MODEL_DIRS:
        langs.append({
            "code": code,
            "name": recognizer.LANG_NAMES.get(code, code),
            "available": recognizer.is_available(code),
        })
    default = DEFAULT_LANG if recognizer.is_available(DEFAULT_LANG) else next(
        (l["code"] for l in langs if l["available"]), None)
    return jsonify({"languages": langs, "default_lang": default, "engine": "vosk"})


@app.route("/api/commands")
def api_commands():
    """Список операций для выбранного языка."""
    lang = request.args.get("lang", DEFAULT_LANG)
    if lang not in cmd.supported_languages():
        lang = DEFAULT_LANG
    return jsonify({
        "lang": lang,
        "commands": cmd.get_commands(lang),
        "essays": [{"id": e["id"], "title": e["title"], "keywords": e["keywords"]}
                   for e in cmd.get_essays()],
    })


@app.route("/api/essays")
def api_essays():
    """Содержимое предметной области (немецкие сочинения)."""
    return jsonify({"essays": cmd.get_essays()})


@app.route("/api/recognize", methods=["POST"])
def api_recognize():
    """WAV с микрофона -> распознанный текст + сопоставленная операция.

    Тело запроса: audio/wav (16-бит PCM). Параметр ?lang=de|en|ru.
    """
    lang = request.args.get("lang", DEFAULT_LANG)
    if not recognizer.is_available(lang):
        return jsonify(error=f"Модель для '{lang}' не установлена",
                       hint=f"uv run python scripts/download_model.py {lang}"), 400

    data = request.get_data()
    if not data:
        return jsonify(error="Пустой аудиопоток"), 400
    if len(data) > MAX_AUDIO_BYTES:
        return jsonify(error="Слишком длинная запись"), 413

    try:
        text = recognizer.recognize_wav(data, lang)
    except Exception as e:  # noqa: BLE001
        return jsonify(error="Ошибка распознавания", detail=str(e)), 500

    matched = cmd.match(text, lang)
    return jsonify({"lang": lang, "text": text, "command": matched})


@app.route("/api/match", methods=["POST"])
def api_match():
    """Сопоставление введённого текста с операцией (проверка без микрофона).

    Тело: JSON {text}. Параметр ?lang=de|en|ru.
    """
    lang = request.args.get("lang", DEFAULT_LANG)
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    return jsonify({"lang": lang, "text": text, "command": cmd.match(text, lang)})


@app.route("/api/tts", methods=["POST"])
def api_tts():
    """Серверный синтез (espeak-ng) для команды «read» — работает в любом браузере.

    Тело: JSON {text, voice?, rate?, pitch?}. Возвращает audio/wav.
    """
    espeak = _espeak_bin()
    if not espeak:
        return jsonify(error="espeak-ng не найден на сервере. Установите: sudo pacman -S espeak-ng"), 500

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify(error="Пустой текст"), 400
    text = text[:MAX_TTS_LEN]

    voice = data.get("voice") or "de"
    rate = max(80, min(400, int(round(_to_float(data.get("rate"), 1.0) * 175))))
    pitch = max(0, min(99, int(round(_to_float(data.get("pitch"), 1.0) * 50))))

    with tempfile.TemporaryDirectory() as d:
        infile = Path(d) / "in.txt"
        outfile = Path(d) / "out.wav"
        infile.write_text(text, encoding="utf-8")
        cmdargs = [espeak, "-v", voice, "-s", str(rate), "-p", str(pitch),
                   "-a", "100", "-w", str(outfile), "-f", str(infile)]
        try:
            subprocess.run(cmdargs, check=True, capture_output=True, timeout=120)
        except subprocess.CalledProcessError as e:
            return jsonify(error="Ошибка espeak-ng",
                           detail=(e.stderr or b"").decode("utf-8", "ignore")), 500
        except subprocess.TimeoutExpired:
            return jsonify(error="Тайм-аут синтеза (слишком длинный текст)"), 500
        wav = outfile.read_bytes()

    return Response(wav, mimetype="audio/wav", headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
