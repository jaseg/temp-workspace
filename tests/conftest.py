import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def pytest_addoption(parser):
    parser.addoption('--full-corpus', action='store_true', help='Run the full layout corpus instead of the quick subset')
