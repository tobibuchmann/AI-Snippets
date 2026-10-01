import importlib.util
import json
import sys
from pathlib import Path

_legacy_path = Path(__file__).resolve().parent.parent / "fulfillment_app.py"
_spec = importlib.util.spec_from_file_location("_geburtstagsquest_legacy", _legacy_path)
_legacy = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _legacy
_spec.loader.exec_module(_legacy)

# Compatibility bridge: the new multi-theme renderer exposes build_premium_pdf,
# while the existing premium module still imports structured_pdf_bytes.
import premium_pdf as _premium_pdf
if not hasattr(_premium_pdf, "structured_pdf_bytes"):
    def _structured_pdf_bytes(payload, generated):
        if isinstance(generated, dict):
            quest = generated
        else:
            try:
                quest = json.loads(generated or "{}")
            except Exception:
                quest = {}
        return _premium_pdf.build_premium_pdf(payload or {}, quest if isinstance(quest, dict) else {})
    _premium_pdf.structured_pdf_bytes = _structured_pdf_bytes

from .premium import install as install_premium
from .quality_v2 import install as install_quality_v2

install_premium(_legacy)
install_quality_v2(_legacy)

try:
    from qa_preview import install_preview
    install_preview(_legacy)
except Exception:
    _legacy.app.logger.exception("QA preview setup failed")

app = _legacy.app
