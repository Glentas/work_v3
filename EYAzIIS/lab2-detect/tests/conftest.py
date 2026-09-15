"""Общая подготовка тестов.

Переменные окружения задаются ДО импорта приложения, потому что
``app/config.py`` читает их на этапе импорта модуля. Тренировочный набор
синтетический, но разделимый: французский с диакритикой, английский без неё.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_SANDBOX = Path(tempfile.mkdtemp(prefix="lab2-tests-"))
os.environ["CORPUS_PATH"] = str(_SANDBOX / "corpus")
os.environ["TRAIN_PATH"] = str(_SANDBOX / "train")
os.environ["TEST_PATH"] = str(_SANDBOX / "test")
os.environ["STRESS_PATH"] = str(_SANDBOX / "stress")

#: Тесты используют настоящую модель, если она скачана; иначе нейросетевые
#: проверки пропускаются, а не падают.
_REAL_MODEL = PROJECT_ROOT / "models" / "lid.176.ftz"
if _REAL_MODEL.exists():
    os.environ.setdefault("MODEL_PATH", str(_REAL_MODEL))
else:
    os.environ["MODEL_PATH"] = str(_SANDBOX / "missing.ftz")

FR_TRAIN = (
    "La forêt et le château sont très beaux. " * 40
    + "Nous avons mangé du gâteau près de la rivière entière. " * 40
)
EN_TRAIN = (
    "The weather in the town is very good today. " * 40
    + "We have walked along the river and the hill with the dog. " * 40
)


def _write_train() -> None:
    train = Path(os.environ["TRAIN_PATH"])
    train.mkdir(parents=True, exist_ok=True)
    (train / "fr.txt").write_text(FR_TRAIN, encoding="utf-8")
    (train / "en.txt").write_text(EN_TRAIN, encoding="utf-8")


_write_train()
