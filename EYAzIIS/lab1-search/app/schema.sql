CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    keywords TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    term TEXT UNIQUE NOT NULL,
    df INTEGER DEFAULT 0,
    idf REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS postings (
    term_id INTEGER NOT NULL,
    doc_id INTEGER NOT NULL,
    tf INTEGER NOT NULL,
    weight REAL NOT NULL,
    PRIMARY KEY (term_id, doc_id),
    FOREIGN KEY (term_id) REFERENCES terms(id),
    FOREIGN KEY (doc_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL,
    params_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(params_json)
);

CREATE TABLE IF NOT EXISTS relevance_marks (
    query_id INTEGER NOT NULL,
    doc_id INTEGER NOT NULL,
    relevant INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (query_id, doc_id),
    FOREIGN KEY (query_id) REFERENCES queries(id),
    FOREIGN KEY (doc_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS query_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL UNIQUE,
    total_found INTEGER NOT NULL,
    total_relevant INTEGER NOT NULL,
    relevant_positions TEXT NOT NULL,
    recall REAL,
    precision REAL,
    avg_prec REAL,
    p5 REAL,
    p10 REAL,
    r_prec REAL,
    pr_curve TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (query_id) REFERENCES queries(id)
);

CREATE TABLE IF NOT EXISTS metrics_summary (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    total_queries INTEGER DEFAULT 0,
    sum_recall REAL DEFAULT 0,
    sum_precision REAL DEFAULT 0,
    sum_avg_prec REAL DEFAULT 0,
    sum_p5 REAL DEFAULT 0,
    sum_p10 REAL DEFAULT 0,
    sum_r_prec REAL DEFAULT 0,
    sum_pr_curve TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_postings_term ON postings(term_id);
CREATE INDEX IF NOT EXISTS idx_postings_doc ON postings(doc_id);
CREATE INDEX IF NOT EXISTS idx_terms_term ON terms(term);
CREATE INDEX IF NOT EXISTS idx_relevance_query ON relevance_marks(query_id);