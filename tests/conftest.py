import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def path(*parts: str) -> str:
    return os.path.join(ROOT, *parts)
