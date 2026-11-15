import configparser
import shutil
import subprocess
from pathlib import Path

from behave import given, then, when


ROOT = Path(__file__).resolve().parents[2]


@given("the plugin metadata")
def read_metadata(context):
    context.metadata = configparser.ConfigParser()
    context.metadata.optionxform = str
    assert context.metadata.read(ROOT / "metadata.txt", encoding="utf-8")


@then("all mandatory metadata fields are present")
def check_metadata(context):
    assert context.metadata.has_section("general")
    for field in ("name", "description", "version", "qgisMinimumVersion", "email", "author"):
        assert context.metadata.has_option("general", field), field


@given("QGIS is initialized")
def init_qgis(context):
    from support.hooks import qgis_app
    qgis_app()


@then("the GDAL, OGR and PostgreSQL providers are available")
def check_providers(context):
    from qgis.core import QgsProviderRegistry
    assert {"gdal", "ogr", "postgres"} <= set(QgsProviderRegistry.instance().providerList())


@when("I load the WGS 84 WKT and sample raster")
def load_crs(context):
    from qgis.core import QgsCoordinateReferenceSystem, QgsRasterLayer

    wkt = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
           'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
           'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')
    context.crs = QgsCoordinateReferenceSystem()
    assert context.crs.createFromWkt(wkt)
    context.raster = QgsRasterLayer(
        str(ROOT / "test" / "fixtures" / "tenbytenraster.asc"),
        "TestRaster"
    )
    assert context.raster.isValid()


@then("both reference systems describe WGS 84")
def check_crs(context):
    assert context.crs.authid() == "EPSG:4326"
    assert context.raster.crs().authid() in ("EPSG:4326", "OGC:CRS84")


@when("I {action} the dialog")
def finish_dialog(context, action):
    if action == "accept":
        context.dialog.accept()
    else:
        assert action == "reject"
        context.dialog.reject()


@then("the dialog result is {result}")
def check_dialog_result(context, result):
    from qgis.PyQt.QtWidgets import QDialog
    expected = {"accepted": QDialog.DialogCode.Accepted, "rejected": QDialog.DialogCode.Rejected}
    assert context.dialog.result() == expected[result]


@when("I compile and install the Afrikaans translation")
def install_translation(context):
    from qgis.PyQt.QtCore import QCoreApplication, QTranslator

    compiler = shutil.which("lrelease") or shutil.which("pyside6-lrelease")
    assert compiler, "Install Qt's lrelease to run the translation scenario"
    output = Path(context.tempdir.name) / "af.qm"
    subprocess.run([compiler, str(ROOT / "i18n" / "af.ts"), "-qm", str(output)], check=True)
    context.translator = QTranslator()
    assert context.translator.load(str(output))
    assert QCoreApplication.installTranslator(context.translator)


@then('"{source}" is translated as "{translation}"')
def check_translation(context, source, translation):
    from qgis.PyQt.QtCore import QCoreApplication
    assert QCoreApplication.translate("@default", source) == translation
