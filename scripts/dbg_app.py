"""Debug: what does `from app.main import app` actually bind? Safe print only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as app_package

print("app package path:", getattr(app_package, "__path__", "NO PATH"))
from app.main import app

print("type:", type(app))
print("repr:", repr(app)[:200])
print("main module file:", sys.modules["app.main"].__file__)
