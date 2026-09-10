-- Структура базы данных информационно-поисковой системы.
--
-- Обозначения из методички:
--   N   — общее число документов в коллекции;
--   P_i — число документов, содержащих термин i;
--   B_i — инверсная частота термина i, B_i = log(N / P_i)      (формула 1.5);
--   Q_i^j — частота термина i в документе j;
--   A_i^j — вес термина i в документе j, A_i^j = Q_i^j * B_i   (формула 1.6).

-- Документ коллекции. Поисковый образ документа (ПОД) хранится в postings.
CREATE TABLE IF NOT EXISTS documents (
    id       INTEGER PRIMARY KEY,
    title    TEXT    NOT NULL,
    text     TEXT    NOT NULL,
    path     TEXT    NOT NULL UNIQUE,
    date     TEXT    NOT NULL,            -- ISO-формат YYYY-MM-DD, сортируется лексикографически
    time     TEXT    NOT NULL,
    words    INTEGER NOT NULL DEFAULT 0,  -- число значимых слов (для диагностики ранжирования)
    keywords TEXT    NOT NULL DEFAULT ''   -- TOP_KEYWORDS слов с наибольшим весом A_i^j
);

-- Словарь терминов (стемм). df = P_i, idf = B_i.
CREATE TABLE IF NOT EXISTS terms (
    id   INTEGER PRIMARY KEY,
    term TEXT    NOT NULL UNIQUE,
    df   INTEGER NOT NULL,
    idf  REAL    NOT NULL
);

-- Инвертированный индекс: posting list каждого термина.
CREATE TABLE IF NOT EXISTS postings (
    term_id INTEGER NOT NULL REFERENCES terms(id)    ON DELETE CASCADE,
    doc_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tf      INTEGER NOT NULL,                        -- Q_i^j
    weight  REAL    NOT NULL,                        -- A_i^j = Q_i^j * B_i
    PRIMARY KEY (term_id, doc_id)
);

-- Запрос пользователя вместе с параметрами поиска.
-- params_json — уникальный ключ: одна и та же настройка запроса
-- всегда соответствует одной строке и одной разметке релевантности.
CREATE TABLE IF NOT EXISTS queries (
    id          INTEGER PRIMARY KEY,
    query_text  TEXT NOT NULL,
    params_json TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

-- Экспертные отметки: какие документы считаются релевантными запросу.
-- Строка существует <=> документ отмечен как релевантный.
CREATE TABLE IF NOT EXISTS relevance_marks (
    query_id INTEGER NOT NULL REFERENCES queries(id)   ON DELETE CASCADE,
    doc_id   INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    PRIMARY KEY (query_id, doc_id)
);

-- Сохранённые оценки качества поиска по методике РОМИП'2004.
CREATE TABLE IF NOT EXISTS query_metrics (
    query_id           INTEGER PRIMARY KEY REFERENCES queries(id) ON DELETE CASCADE,
    total_found        INTEGER NOT NULL,   -- a + b: сколько документов выдала система
    total_relevant     INTEGER NOT NULL,   -- a + c: сколько отмечено релевантными
    found_relevant     INTEGER NOT NULL,   -- a:     релевантных среди выданных
    relevant_positions TEXT    NOT NULL,   -- JSON: позиции релевантных документов (1-based)
    recall             REAL,               -- a / (a + c)
    precision          REAL,               -- a / (a + b)
    f_measure          REAL,               -- 2pr / (p + r)
    avg_prec           REAL,               -- средняя точность
    p5                 REAL,               -- точность на уровне 5 документов
    p10                REAL,               -- точность на уровне 10 документов
    r_prec             REAL,               -- R-точность
    pr_curve           TEXT,               -- JSON: 11 интерполированных значений точности
    created_at         TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_postings_doc      ON postings(doc_id);
CREATE INDEX IF NOT EXISTS idx_relevance_doc     ON relevance_marks(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_date    ON documents(date);
