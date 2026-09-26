-- Структура базы данных системы машинного перевода (лр. №4, вариант 7).
--
-- entries   — двуязычный словарь: английский источник -> русский эквивалент.
-- sessions  — сохранённые сессии перевода (результат целиком в JSON).

-- Запись словаря.
--   source — английская лемма или оборот (леммы через пробел, «пословно-
--            оборотный» учёт локального контекста);
--   pos    — универсальная часть речи (NOUN/VERB/ADJ/...) или PHRASE;
--   target — русский эквивалент: существительные в им. п. ед. ч., глаголы в
--            инфинитиве, прилагательные в м. р., предлоги и т. д.;
--   gram   — JSON с грамматической информацией для морфологического синтеза:
--            существительные: {"gender": "m|f|n", "anim": bool, "inv": bool,
--                              "pl": "...", "gpl": "...", "forms": {...}}
--            глаголы:        {"aspect": "impf|pf", "pair": "сов. вид",
--                              "pp": "краткое причастие", "forms": {...}}
--            предлоги:       {"gov": "gen|dat|acc|inst|prep"}
--            прилагательные: {"comp": "...", "sup": "..."}
--   domain — предметная область: general | med | art (вариант 7);
--   verified — 0, если запись добавлена утилитой автоматического пополнения
--            и ещё не проверена пользователем, иначе 1.
CREATE TABLE IF NOT EXISTS entries (
    id         INTEGER PRIMARY KEY,
    source     TEXT    NOT NULL,
    pos        TEXT    NOT NULL DEFAULT '',
    target     TEXT    NOT NULL DEFAULT '',
    gram       TEXT    NOT NULL DEFAULT '{}',
    domain     TEXT    NOT NULL DEFAULT 'general',
    verified   INTEGER NOT NULL DEFAULT 1,
    note       TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    UNIQUE (source, pos, domain)
);

CREATE INDEX IF NOT EXISTS idx_entries_source ON entries(source);
CREATE INDEX IF NOT EXISTS idx_entries_domain ON entries(domain);

-- Сессия перевода: одна строка = один переведённый текст.
-- result_json — сериализованная TranslationResult (перевод, статистика,
-- частотный список вкладки 1 и деревья разбора вкладки 2).
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    mode        TEXT    NOT NULL DEFAULT 'transfer',
    domain      TEXT    NOT NULL DEFAULT 'general',
    created_at  TEXT    NOT NULL,
    source_text TEXT    NOT NULL,
    result_json TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
