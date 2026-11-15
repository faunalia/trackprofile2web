import json
import importlib
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

from behave import given, then, when


ROOT = Path(__file__).resolve().parents[2]
COORDINATES = [[12.0, 45.0, 100.0], [12.01, 45.01, 200.0]]
def create_layer(context, geometry_type, crs, wkt):
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    from support.hooks import qgis_app
    qgis_app()
    TrackProfile2webDialog = importlib.import_module(
        ROOT.name + ".track_profile_2_web_dialog"
    ).TrackProfile2webDialog

    context.layer = QgsVectorLayer(
        geometry_type + "?crs=" + crs,
        "Test track", "memory"
    )
    feature = QgsFeature(context.layer.fields())
    feature.setGeometry(QgsGeometry.fromWkt(wkt))
    context.layer.dataProvider().addFeatures([feature])
    QgsProject.instance().addMapLayer(context.layer)
    context.dialog = TrackProfile2webDialog()
    context.load_results = []
    context.dialog.mapview.loadFinished.connect(context.load_results.append)
    context.renderer_errors = []
    context.dialog.mapview.renderProcessTerminated.connect(
        lambda status, code: context.renderer_errors.append((status, code))
    )
    context.dialog.layer_combo.setLayer(context.layer)


@given("a QGIS line layer {elevation}")
def line_layer(context, elevation):
    has_z = elevation == "with elevations"
    create_layer(context, "LineStringZ" if has_z else "LineString", "EPSG:4326",
                 "LINESTRING Z (12 45 100, 12.01 45.01 200)" if has_z
                 else "LINESTRING (12 45, 12.01 45.01)")


@given("a projected multipart QGIS line layer with elevations")
def projected_layer(context):
    create_layer(context, "MultiLineStringZ", "EPSG:3857",
                 "MULTILINESTRING Z ((0 0 100, 111319.490793 0 200), "
                 "(0 0 300, 0 111325.142866 400))")


@when("I update the preview")
def update_preview(context):
    if not getattr(context, "mapterhorn_mock", False):
        context.dialog.changeMap()
        return

    module = importlib.import_module(ROOT.name + ".track_profile_2_web_dialog")
    image = context.mapterhorn_image
    with patch.object(
        module,
        "_fetch_mapterhorn_tile",
        side_effect=lambda zoom, x, y: image if zoom == 13 else None
    ):
        context.dialog.changeMap()


@when("Mapterhorn elevation tiles are available")
def mapterhorn_tiles_available(context):
    from qgis.PyQt.QtGui import QColor, QImage

    context.mapterhorn_mock = True
    context.mapterhorn_image = QImage(512, 512, QImage.Format.Format_RGB32)
    context.mapterhorn_image.fill(QColor(128, 100, 0))


@when("Mapterhorn elevation tiles are unavailable")
def mapterhorn_tiles_unavailable(context):
    context.mapterhorn_mock = True
    context.mapterhorn_image = None


@then("the preview contains the Mapterhorn elevations")
def check_mapterhorn_preview(context):
    data = json.loads(context.dialog.opts["elevationControl"]["data"])
    assert data["features"][0]["geometry"]["coordinates"] == [
        [12.0, 45.0, 100.0],
        [12.01, 45.01, 100.0],
    ]


@then("the original layer remains 2D")
def check_source_layer_is_unchanged(context):
    from qgis.core import QgsWkbTypes

    assert not QgsWkbTypes.hasZ(context.layer.wkbType())
    assert QgsWkbTypes.hasZ(context.dialog.vlayer.wkbType())
    assert "Mapterhorn" in context.dialog.opts["otmLayer"]["options"]["attribution"]


@then("the exported GeoJSON contains the Mapterhorn elevations")
def check_mapterhorn_export(context):
    data = json.loads(
        (Path(context.tempdir.name) / "Test-track.geojson").read_text(encoding="utf-8")
    )
    assert data["features"][0]["geometry"]["coordinates"] == [
        [12.0, 45.0, 100.0],
        [12.01, 45.01, 100.0],
    ]


@when("the plugin is loaded and unloaded")
def load_plugin(context):
    context.iface = MagicMock()
    context.iface.mainWindow.return_value = None
    plugin = importlib.import_module(ROOT.name).classFactory(context.iface)
    plugin.initGui()
    assert not plugin.actions[0].icon().isNull()
    plugin.unload()


@then("its menu and toolbar actions are registered and removed")
def check_plugin_actions(context):
    context.iface.addPluginToWebMenu.assert_called_once()
    context.iface.addToolBarIcon.assert_called_once()
    context.iface.removePluginWebMenu.assert_called_once()
    context.iface.removeToolBarIcon.assert_called_once()


@then("the preview contains the line coordinates and elevations")
def check_preview(context):
    data = json.loads(context.dialog.opts["elevationControl"]["data"])
    assert data["features"][0]["geometry"]["coordinates"] == COORDINATES
    assert Path(context.dialog.fout).is_file()


@then("the export buttons are enabled")
def exports_enabled(context):
    assert context.dialog.export_btn.isEnabled()
    assert context.dialog.export_geojson_btn.isEnabled()


@then("the QGIS preview displays the elevation chart")
def check_qgis_chart(context):
    from qgis.PyQt.QtCore import QEventLoop, QTimer

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        result = []
        loop = QEventLoop()
        def finish(value, result=result, loop=loop):
            result.append(value)
            loop.quit()
        context.dialog.mapview.page().runJavaScript(
            """JSON.stringify({ready: document.readyState, value: document.querySelector('.maxele .summaryvalue')?.textContent, leaflet: typeof L, url: location.href})""", finish
        )
        QTimer.singleShot(1000, loop.quit)
        loop.exec()
        if result and result[0] and json.loads(result[0]).get("value") == "200.00 m":
            return
        if context.renderer_errors:
            break
        loop = QEventLoop()
        QTimer.singleShot(200, loop.quit)
        loop.exec()
    raise AssertionError("QGIS preview did not render: load: {}; renderer: {}; state: {}".format(
        context.load_results, context.renderer_errors, result))


@then("the export buttons remain disabled")
def exports_disabled(context):
    assert not context.dialog.export_btn.isEnabled()
    assert not context.dialog.export_geojson_btn.isEnabled()


@when("I export the HTML and GeoJSON")
def export_geojson(context):
    from qgis.PyQt.QtWidgets import QFileDialog
    with patch.object(QFileDialog, "getExistingDirectory", return_value=context.tempdir.name):
        context.dialog.saveAsHtmlGeojson()


@then("the HTML references the exported GeoJSON")
def check_export(context):
    folder = Path(context.tempdir.name)
    html = (folder / "Test-track.html").read_text(encoding="utf-8")
    data = json.loads((folder / "Test-track.geojson").read_text(encoding="utf-8"))
    assert "Test-track.geojson" in html
    assert data["features"][0]["geometry"]["coordinates"] == COORDINATES


@then("the preview still contains embedded data")
def check_embedded_data(context):
    assert json.loads(context.dialog.opts["elevationControl"]["data"])["type"] == "FeatureCollection"


@when("I export the single HTML file")
def export_html(context):
    from qgis.PyQt.QtWidgets import QFileDialog
    path = str(Path(context.tempdir.name) / "track.html")
    with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "*.html")):
        context.dialog.saveAsHtml()


@then("the exported HTML contains the embedded track")
def check_html(context):
    html = (Path(context.tempdir.name) / "track.html").read_text(encoding="utf-8")
    assert "Test track" in html
    assert "100.0" in html


@then("both outputs contain separate reprojected line parts")
def check_reprojected_parts(context):
    preview = json.loads(context.dialog.opts["elevationControl"]["data"])
    exported = json.loads((Path(context.tempdir.name) / "Test-track.geojson").read_text(encoding="utf-8"))
    for data in (preview, exported):
        geometry = data["features"][0]["geometry"]
        assert geometry["type"] == "MultiLineString"
        parts = geometry["coordinates"]
        assert len(parts) == 2
        assert abs(parts[0][1][0] - 1) < 0.000001
        assert abs(parts[1][1][1] - 1) < 0.000001
        assert parts[0][0][2] == 100
        assert parts[1][0][2] == 300


def prepare_web_profile(context, separate, detached=True):
    data = {
        "type": "FeatureCollection",
        "name": "Test track",
        "features": [{"type": "Feature", "properties": {},
                      "geometry": {"type": "LineString", "coordinates": COORDINATES}}],
    }
    folder = Path(context.tempdir.name)
    if separate:
        (folder / "track.geojson").write_text(json.dumps(data), encoding="utf-8")
    opts = {
        "map": {"center": [45, 12], "zoom": 10, "zoomControl": False},
        "zoomControl": {"position": "topleft"},
        "otmLayer": {"url": "", "options": {}},
        "layersControl": {"options": {"collapsed": True}},
        "elevationControl": {
            "data": "track.geojson" if separate else json.dumps(data),
            "options": {"theme": "custom-theme", "detached": detached,
                        "elevationDiv": "#elevation-div", "followMarker": False,
                        "hotline": False, "distanceMarkers": False, "edgeScale": False,
                        "summary": False, "downloadLink": False}
        }
    }
    html = (ROOT / "template.html").read_text(encoding="utf-8")
    html = html.replace("'{ py_opts }'", json.dumps(opts))
    for name, value in {
        "area_fill_color": "#d45f5f", "area_stroke_width": "2.5",
        "marker_color": "#ffb800", "line_color": "#ff0000", "line_opacity": "0.85"
    }.items():
        html = html.replace("{ " + name + " }", value)
    (folder / "profile.html").write_text(html, encoding="utf-8")


@given("an embedded elevation profile in the HTML template")
def embedded_profile(context):
    prepare_web_profile(context, False)


@given("an elevation profile in a separate GeoJSON file")
def separate_profile(context):
    prepare_web_profile(context, True)


@given("an attached elevation profile in the HTML template")
def attached_profile(context):
    prepare_web_profile(context, False, detached=False)


@when("I open the profile in a browser")
def open_profile(context):
    from playwright.sync_api import sync_playwright

    handler = partial(SimpleHTTPRequestHandler, directory=context.tempdir.name)
    context.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    context.server_thread = threading.Thread(target=context.server.serve_forever, daemon=True)
    context.server_thread.start()
    context.playwright = sync_playwright().start()
    context.browser = context.playwright.chromium.launch(channel="chrome", headless=True)
    context.page = context.browser.new_page(ignore_https_errors=True)
    context.page.goto("http://127.0.0.1:{}/profile.html".format(context.server.server_port))


@then("the chart and its elevation summary are displayed")
def check_chart(context):
    context.page.wait_for_function(
        "document.querySelector('.maxele .summaryvalue').textContent === '200.00 m'",
        timeout=30000
    )
    assert context.page.locator(".custom-theme.elevation-control .area path.altitude").count() > 0
    assert context.page.locator(".minele .summaryvalue").inner_text() == "100.00 m"


@then("the profile is attached to the map")
def check_attached(context):
    assert context.page.locator("#map .custom-theme.elevation-control").count() == 1
