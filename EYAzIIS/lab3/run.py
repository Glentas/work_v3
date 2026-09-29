# -*- coding: utf-8 -*-
"""Точка входа: python run.py [порт]."""
import os
import sys

import uvicorn

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False)
