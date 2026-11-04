#!/usr/bin/env bash
# Регулярное обновление датасета (Вариант 1 — официальная статистика Белстата).
#
# Пайплайн идемпотентен: повторный прогон перезаписывает строки по тем же
# показателям, поэтому скрипт можно ставить в cron хоть каждый день.
# Белстат публикует годовые данные раз в год (обычно март–май), так что
# разумная частота — раз в неделю.
#
# Использование:
#   ./scripts/update_dataset.sh                 # весь раздел правонарушений
#   ./scripts/update_dataset.sh 2015-2025       # ограничить период
#
set -euo pipefail

cd "$(dirname "$0")/.."

YEARS="${1:-}"
OUT_DIR="${OUT_DIR:-data}"
DB_PATH="${DB_PATH:-${OUT_DIR}/belstat_crime.sqlite}"
LOG_DIR="${LOG_DIR:-logs}"
mkdir -p "$OUT_DIR" "$LOG_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
ARGS=(collect --out "$OUT_DIR" --db "$DB_PATH" --delay 0.8 -v)
if [[ -n "$YEARS" ]]; then
  ARGS+=(--years "$YEARS")
fi

echo "[$(date -Is)] запуск: python -m belstat_dataset ${ARGS[*]}"
if python3 -m belstat_dataset "${ARGS[@]}" 2>&1 | tee "${LOG_DIR}/collect-${STAMP}.log"; then
  echo "[$(date -Is)] готово. Отчёт: ${OUT_DIR}/REPORT.md"
else
  echo "[$(date -Is)] ОШИБКА сбора — см. ${LOG_DIR}/collect-${STAMP}.log" >&2
  exit 1
fi
