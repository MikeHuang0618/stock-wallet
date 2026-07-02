"""讓 tests/ 內的測試能 import 專案根目錄的純邏輯模組(wallet / indicators / analysis)。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
