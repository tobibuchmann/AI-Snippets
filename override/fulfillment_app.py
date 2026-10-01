"""Render entrypoint that preserves the stable fulfillment core and swaps only the PDF renderer."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = ROOT / "fulfillment_app.py"
PREMIUM_PATH = ROOT / "premium_pdf.py"

core_spec = spec_from_file_location("geburtstagsquest_core", CORE_PATH)
core = module_from_spec(core_spec)
sys.modules["geburtstagsquest_core"] = core
core_spec.loader.exec_module(core)

premium_spec = spec_from_file_location("geburtstagsquest_premium_pdf", PREMIUM_PATH)
premium = module_from_spec(premium_spec)
sys.modules["geburtstagsquest_premium_pdf"] = premium
premium_spec.loader.exec_module(premium)

# Existing fulfillment functions resolve this module global at runtime.
core.structured_pdf_bytes = premium.structured_pdf_bytes
app = core.app
