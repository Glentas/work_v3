"""Сохранение и печать результатов перевода (требование ТЗ).

Результаты перевода и упорядоченный по частоте список слов с переводами и
грамматической информацией сохраняются в файл формата TXT кодировки
Unicode (UTF-8 с BOM — «utf-8-sig», корректно открывается «Блокнотом»
Windows и всеми современными редакторами).
"""

from __future__ import annotations

from . import config, tree
from .domain import TranslationResult
from .grammar import pos_rus

LINE = "─" * 78


def build_txt(result: TranslationResult) -> str:
    """Полный текстовый отчёт по сессии перевода (кодировка Unicode)."""
    lines: list[str] = []
    stats = result.stats

    lines.append(config.APP_TITLE.upper())
    lines.append(config.APP_VARIANT)
    lines.append("")
    lines.append(f"Сессия:            {result.name}")
    lines.append(f"Дата:              {result.created_at}")
    lines.append(f"Режим перевода:    {config.MODE_NAMES.get(result.mode, result.mode)}")
    lines.append(f"Предметная область: {config.DOMAIN_NAMES.get(result.domain, result.domain)}")
    lines.append(f"Языковая пара:     {config.SOURCE_LANG_NAME} -> {config.TARGET_LANG_NAME}")
    lines.append("")
    lines.append(LINE)
    lines.append("ИСХОДНЫЙ ТЕКСТ")
    lines.append(LINE)
    lines.append(result.source_text)
    lines.append("")
    lines.append(LINE)
    lines.append(f"ПЕРЕВОД ({config.TARGET_LANG_NAME.upper()})")
    lines.append(LINE)
    for sent in result.sentences:
        lines.append(sent.translation)
    lines.append("")
    lines.append(LINE)
    lines.append("СТАТИСТИКА ПЕРЕВОДА")
    lines.append(LINE)
    lines.append(f"Количество слов во входном тексте:  {stats.total_words}")
    lines.append(f"Количество переведённых слов:       {stats.translated_words}"
                 f"  (покрытие {stats.coverage * 100:.1f} %)")
    lines.append(f"Чисел (переносятся как есть):       {stats.digits}")
    lines.append(f"Предложений:                        {stats.sentences}")
    lines.append(f"Время анализа и перевода:           {stats.duration_ms:.0f} мс")
    lines.append(f"Записей в словаре:                  {stats.dict_size}")
    lines.append(f"Неизвестных слов (вхождений):       {stats.unknown_total}")
    if stats.unknown:
        lines.append("Неизвестные слова: " + ", ".join(stats.unknown))
    lines.append("")
    lines.append(LINE)
    lines.append("СПИСОК СЛОВ ПО ЧАСТОТЕ ВСТРЕЧАЕМОСТИ (вкладка 1)")
    lines.append(LINE)
    header = (f"{'№':>4} | {'Част.':>5} | {'Лемма':<18} | {'Словоформы':<24} | "
              f"{'Ч.Р.':<6} | {'Тег':<5} | {'Расшифровка тега':<44} | "
              f"{'Роль':<9} | {'Расшифровка роли':<44} | Перевод")
    lines.append(header)
    lines.append("-" * len(header))
    for i, row in enumerate(result.freq, start=1):
        forms = ", ".join(row.forms[:6])
        lines.append(
            f"{i:>4} | {row.freq:>5} | {row.lemma:<18} | {forms:<24} | "
            f"{pos_rus(row.pos):<6} | {row.tag:<5} | {row.tag_ru:<44} | "
            f"{row.dep:<9} | {row.dep_ru:<44} | {row.translation or '— (нет в словаре)'}"
        )
    lines.append("")
    lines.append(LINE)
    lines.append("ДЕРЕВЬЯ СИНТАКСИЧЕСКОГО РАЗБОРА (вкладка 2)")
    lines.append(LINE)
    for sent in result.sentences:
        lines.append("")
        lines.append(f"Предложение {sent.id + 1}: {sent.text}")
        lines.append(f"Перевод:    {sent.translation}")
        lines.append(tree.tree_text(sent.tokens))
    lines.append("")
    lines.append(LINE)
    lines.append(f"Файл сформирован системой «{config.APP_TITLE}».")
    return "\n".join(lines)


def txt_filename(result: TranslationResult) -> str:
    """Имя файла результата (только ASCII — ограничение HTTP-заголовков)."""
    base = "".join(ch for ch in result.name if ch.isascii() and (ch.isalnum() or ch in "-_"))
    stamp = "".join(ch for ch in result.created_at if ch.isdigit())[:12]
    return f"perevod_{base or 'session'}{'_' + stamp if stamp else ''}.txt"
