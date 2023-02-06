#!/usr/bin/env python3
"""Runtime constants used throughout the package."""
import os

AREA_CONFIG_PATH = os.environ.get("PYTROLL_CONFIG_DIR", "../bin/")

_DEFAULT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

_DEFAULT_LOG_FORMAT = "[%(levelname)s: %(asctime)s : %(name)s] %(message)s"

METOPS = {
    "METOPA": "Metop-A",
    "metopa": "Metop-A",
    "METOPB": "Metop-B",
    "metopb": "Metop-B",
    "metopc": "Metop-C",
    "METOPC": "Metop-C",
}

METOP_LETTER = {"Metop-A": "a", "Metop-B": "b", "Metop-C": "c"}
