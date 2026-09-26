"""Морфологический и синтаксический анализ входного текста (этап анализа).

Используется модель spaCy ``en_core_web_sm`` — та же функциональность, что
в лр. №3 весеннего семестра: сентенс-сегментация, лемматизация, теги частей
речи Penn Treebank, синтаксические роли зависимостей и морфологические
признаки (время, лицо, число, определённость и т. д.).

Модель скачивается один раз скриптом ``scripts/download_model.py``; если её
нет, модуль поднимает ``SpacyUnavailable`` с подсказкой — интерфейс системы
показывает её пользователю вместо падения.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from . import config, grammar
from .domain import SentenceData, TextData, TokenData

log = logging.getLogger(__name__)

#: Индекс родителя для корня предложения (как ROOT_IDX в лр. №3).
ROOT_IDX = -1

_nlp = None


class SpacyUnavailable(RuntimeError):
    """Модель spaCy не загружена — нужен scripts/download_model.py."""


def get_nlp():
    """Ленивая загрузка модели spaCy (один раз на процесс)."""
    global _nlp
    if _nlp is None:
        try:
            import spacy
        except ImportError as exc:  # pragma: no cover - зависит от окружения
            raise SpacyUnavailable(
                "Библиотека spaCy не установлена: выполните `uv sync` "
                "(или pip install -e .) в каталоге lab4-translate."
            ) from exc
        try:
            _nlp = spacy.load(config.SPACY_MODEL)
        except OSError as exc:
            raise SpacyUnavailable(
                f"Модель {config.SPACY_MODEL} не найдена. Выполните один раз: "
                "python scripts/download_model.py"
            ) from exc
    return _nlp


def available() -> bool:
    """Доступна ли модель анализа (для диагностики при старте и в тестах)."""
    try:
        get_nlp()
        return True
    except SpacyUnavailable:
        return False


def _token_kind(token) -> str:
    if token.is_space or not token.text.strip():
        return "punct"
    # Словесные числительные (one, two) считаются словами: они переводятся
    # по словарю и управляют падежом существительного («два пациента»).
    if token.like_num and any(ch.isdigit() for ch in token.text):
        return "digit"
    if token.pos_ in ("PUNCT", "SYM", "SPACE") or token.is_punct:
        return "punct"
    return "word"


def parse_sentence(sent, sent_id: int) -> SentenceData:
    """Разбор одного предложения: токены с тегами, ролями и признаками."""
    tokens: list[TokenData] = []
    base = sent.start  # абсолютный индекс первого токена предложения в doc
    for token in sent:
        kind = _token_kind(token)
        lemma = token.lemma_.lower().strip() or token.text.lower()
        if lemma == "-pron-":  # поведение старых версий spaCy
            lemma = token.text.lower()
        head_id = ROOT_IDX if token.head == token else token.head.i - base
        tokens.append(
            TokenData(
                id=token.i - base,
                word=token.text,
                lemma=lemma,
                pos=token.pos_,
                pos_ru=grammar.pos_rus(token.pos_),
                tag=token.tag_,
                tag_ru=grammar.tag_rus(token.tag_),
                dep=token.dep_,
                dep_ru=grammar.dep_rus(token.dep_),
                head_id=head_id,
                feats={k: v for k, v in token.morph.to_dict().items()},
                kind=kind,
            )
        )
    return SentenceData(id=sent_id, text=sent.text.strip(), tokens=tokens)


def parse_text(text: str) -> tuple[TextData, float]:
    """Полный разбор текста; возвращает (TextData, длительность в секундах)."""
    if not text or not text.strip():
        raise ValueError("Пустой входной текст")
    nlp = get_nlp()
    start = time.time()
    doc = nlp(text)
    sentences = [parse_sentence(sent, i) for i, sent in enumerate(doc.sents)]
    duration = time.time() - start
    text_data = TextData(
        meta={
            "source_language": config.SOURCE_LANG_NAME,
            "model_used": config.SPACY_MODEL,
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "total_sentences": len(sentences),
        },
        sentences=sentences,
    )
    return text_data, duration
