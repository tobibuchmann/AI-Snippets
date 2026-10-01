import importlib.util
import sys
from pathlib import Path

_legacy_path = Path(__file__).resolve().parent.parent / "fulfillment_app.py"
_spec = importlib.util.spec_from_file_location("_geburtstagsquest_legacy", _legacy_path)
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _legacy
_spec.loader.exec_module(_legacy)

from .premium import install

install(_legacy)
app = _legacy.app
