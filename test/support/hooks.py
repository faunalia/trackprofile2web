import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent))
if os.environ.get("QGIS_PREFIX_PATH"):
    sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python" / "plugins"))

QGIS_APP = None


def qgis_app():
    global QGIS_APP
    if QGIS_APP is None:
        # Qt WebEngine must be imported before creating the application.
        from qgis.PyQt import QtWebEngineWidgets
        from qgis.core import QgsApplication
        QGIS_APP = QgsApplication.instance()
        if QGIS_APP is None:
            QGIS_APP = QgsApplication([os.fsencode(sys.executable)], True)
            QGIS_APP.initQgis()
    return QGIS_APP


def before_scenario(context, scenario):
    context.tempdir = tempfile.TemporaryDirectory()


def after_scenario(context, scenario):
    if hasattr(context, "browser"):
        context.browser.close()
        context.playwright.stop()
    if hasattr(context, "server"):
        context.server.shutdown()
        context.server.server_close()
        context.server_thread.join()
    if hasattr(context, "dialog"):
        context.dialog.close()
        context.dialog.preview_dir.cleanup()
        from qgis.core import QgsProject
        QgsProject.instance().clear()
    context.tempdir.cleanup()
