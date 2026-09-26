#!/usr/bin/env python3
"""Создание базы данных и посев начального словаря из data/seed_dictionary.tsv.

Выполняется автоматически при первом старте сервера (app/main.py), но можно
запустить и вручную — например, после правки TSV-файла:

    python scripts/seed_dictionary.py          # дополнить новыми записями
    python scripts/seed_dictionary.py --reset  # пересоздать словарь с нуля

Сессии перевода (--reset не трогает таблицу sessions только с флагом --keep-sessions).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db, dictionary  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Посев словаря системы перевода")
    parser.add_argument("--reset", action="store_true",
                        help="очистить таблицу entries перед посевом")
    parser.add_argument("--keep-sessions", action="store_true",
                        help="при --reset не удалять сохранённые сессии перевода")
    args = parser.parse_args()

    config.ensure_dirs()
    db.init_db()

    if args.reset:
        with db.connect() as conn, db.transaction(conn):
            conn.execute("DELETE FROM entries")
            if not args.keep_sessions:
                conn.execute("DELETE FROM sessions")
        dictionary.invalidate_cache()
        print("таблица entries очищена")

    added = dictionary.seed_from_tsv()
    total = dictionary.count_entries()
    by_domain = {d: dictionary.count_entries(d) for d in config.DOMAINS}
    print(f"добавлено записей: {added}")
    print(f"всего в словаре:   {total}")
    for domain, count in by_domain.items():
        print(f"  {config.DOMAIN_NAMES[domain]:<45} {count}")


if __name__ == "__main__":
    main()
