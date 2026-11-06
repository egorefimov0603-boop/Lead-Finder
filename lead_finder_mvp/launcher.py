import os
import sys
from pathlib import Path

# Keep the database beside the EXE, not in PyInstaller's temporary folder.
if getattr(sys, "frozen", False):
    app_dir = Path(sys.executable).resolve().parent
    bundle_dir = Path(getattr(sys, "_MEIPASS", app_dir))
else:
    app_dir = Path(__file__).resolve().parent
    bundle_dir = app_dir

os.chdir(app_dir)
app_file = bundle_dir / "app.py"

os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

from streamlit.web import cli as stcli

sys.argv = [
    "streamlit",
    "run",
    str(app_file),
    "--global.developmentMode=false",
    "--server.headless=true",
]
stcli.main()
