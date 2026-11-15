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
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer
    from support.hooks import qgis_app
    qgis_app()
    TrackProfile2webDialog = importlib.import_module(
        ROOT.name + ".track_profile_2_web"
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
    deadline = time.monotonic() + 15
    while context.dialog.settings is None and time.monotonic() < deadline:
        loop = QEventLoop()
        QTimer.singleShot(100, loop.quit)
        loop.exec()
    assert context.dialog.settings is not None, "The HTML settings did not initialize"


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

    module = importlib.import_module(ROOT.name + ".track_profile_2_web")
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


@then("the HTML controls change the preview and export a clean page")
def check_html_controls(context):
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from qgis.PyQt.QtWidgets import QFileDialog
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

    def evaluate(script):
        result = []
        loop = QEventLoop()
        context.dialog.mapview.page().runJavaScript(
            script, lambda value: (result.append(value), loop.quit())
        )
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        assert result, "The HTML interface did not respond"
        return result[0]

    def wait_until(script):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if evaluate(script):
                return
            loop = QEventLoop()
            QTimer.singleShot(150, loop.quit)
            loop.exec()
        raise AssertionError("HTML interface did not reach expected state: " + script)

    assert evaluate("""(() => {
      const panel = document.querySelector('#settings-panel');
      return !panel.hidden && getComputedStyle(panel).display !== 'none'
        && !document.querySelector('#panel-toggle, #panel-close');
    })()"""), "settings must be visible without toggle controls at startup"
    context.dialog.show()
    wait_until("document.querySelector('#layer')?.value && !document.querySelector('[data-action=html]')?.disabled")
    assert context.dialog.mapview.width() == context.dialog.width(), "webview width"
    assert context.dialog.mapview.height() == context.dialog.height(), (
        context.dialog.mapview.height(), context.dialog.height()
    )
    assert evaluate("document.querySelector('#layer').selectedOptions[0].textContent") == "Test track", "layer"
    assert evaluate("document.querySelector('#preview').src.includes('template.html')"), "preview URL"
    assert evaluate("document.querySelector('#preview').getBoundingClientRect().height === innerHeight"), "preview height"
    wait_until("!!document.querySelector('#preview').contentWindow.controlLayer")
    assert evaluate("""(() => {
      const frame = document.querySelector('#preview').getBoundingClientRect();
      const panel = document.querySelector('#settings-panel').getBoundingClientRect();
      return panel.left === frame.right && panel.right === innerWidth
        && panel.top === 0 && panel.bottom === innerHeight && frame.width > 0;
    })()"""), "settings must occupy a separate full-height right sidebar"
    assert evaluate("""
        (() => {
          const doc = document.querySelector('#preview').contentDocument;
          const corner = doc.querySelector('.leaflet-top.leaflet-right');
          const panel = document.querySelector('#settings-panel').getBoundingClientRect();
          const controls = [...corner.querySelectorAll('.leaflet-control')];
          const overlaps = (a, b) => a.left < b.right && a.right > b.left
            && a.top < b.bottom && a.bottom > b.top;
          return !doc.querySelector('[aria-label="Settings & export"]')
            && controls.every(control => !overlaps(panel, control.getBoundingClientRect()))
            && doc.documentElement.scrollHeight <= doc.documentElement.clientHeight
            && document.documentElement.scrollHeight <= document.documentElement.clientHeight;
        })()
    """), "Leaflet control placement and page overflow"
    evaluate("document.querySelector('#preview').contentWindow.controlLayer.expand(); true")
    wait_until("""(() => {
      const doc = document.querySelector('#preview').contentDocument;
      const panel = document.querySelector('#settings-panel').getBoundingClientRect();
      const layers = doc.querySelector('.leaflet-control-layers').getBoundingClientRect();
      return panel.right <= layers.left || panel.left >= layers.right
        || panel.bottom <= layers.top || panel.top >= layers.bottom;
    })()""")
    evaluate("document.querySelector('#preview').contentWindow.controlLayer.collapse(); true")
    evaluate("""
        (() => {
          for (const [id, value] of [
            ['basemap', 'OpenStreetMap'], ['profileColor', '#00ff00'],
            ['lineColor', '#0033ff'], ['markerColor', '#ff00ff'],
            ['profileWidth', '4'], ['markerOpacity', '0.5'], ['position', 'bottomleft']
          ]) {
            const input = document.getElementById(id);
            input.value = value;
            input.dispatchEvent(new Event('change'));
          }
          for (const [id, value] of [
            ['detached', false], ['follow', true], ['collapseProfile', true],
            ['autohide', true], ['collapseLayers', true]
          ]) {
            const input = document.getElementById(id);
            input.checked = value;
            input.dispatchEvent(new Event('change'));
          }
          return true;
        })()
    """)
    wait_until("document.querySelector('[data-action=html]').disabled")
    wait_until("!document.querySelector('[data-action=html]').disabled")
    assert context.dialog.settings["basemap"] == "OpenStreetMap", "basemap"
    assert context.dialog.settings["profileColor"] == "#00ff00", "profile color"
    assert "#00ff00" in Path(context.dialog.fout).read_text(encoding="utf-8"), "generated preview color"
    options = context.dialog.opts["elevationControl"]["options"]
    assert not options["detached"] and options["followMarker"] and options["autohide"]
    assert options["position"] == "bottomleft" and options["collapsed"]
    assert context.dialog.opts["layersControl"]["options"]["collapsed"]
    assert context.dialog.settings["lineColor"] == "#0033ff"
    assert context.dialog.settings["markerColor"] == "#ff00ff"
    assert context.dialog.settings["profileWidth"] == 4
    assert context.dialog.settings["markerOpacity"] == 0.5
    wait_until("""(() => {
      const frame = document.querySelector('#preview');
      return frame.contentWindow.opts?.elevationControl.options.position === 'bottomleft'
        && frame.contentWindow.map.getSize().x === frame.clientWidth
        && !document.querySelector('#settings-panel').hidden
        && !frame.contentDocument.querySelector('[aria-label="Settings & export"]');
    })()""")

    evaluate("""(() => {
      const detached = document.querySelector('#detached');
      detached.checked = true;
      detached.dispatchEvent(new Event('change'));
      return true;
    })()""")
    wait_until("""(() => {
      const frame = document.querySelector('#preview');
      return frame.contentWindow.opts?.elevationControl.options.detached
        && !!frame.contentDocument.querySelector('#elevation-div svg.background')
        && !document.querySelector('#settings-panel').hidden
        && !frame.contentDocument.querySelector('[aria-label="Settings & export"]');
    })()""")
    assert evaluate("""(() => {
      const frame = document.querySelector('#preview');
      const doc = frame.contentDocument;
      const chart = doc.querySelector('#elevation-div svg.background').getBoundingClientRect();
      const summary = doc.querySelector('#data-summary').getBoundingClientRect();
      return chart.right <= frame.clientWidth && chart.bottom <= summary.top
        && doc.documentElement.scrollWidth <= doc.documentElement.clientWidth
        && doc.documentElement.scrollHeight <= doc.documentElement.clientHeight;
    })()"""), "detached chart must fit beside the sidebar"
    other = QgsVectorLayer("LineStringZ?crs=EPSG:4326", "Other track", "memory")
    feature = QgsFeature(other.fields())
    feature.setGeometry(QgsGeometry.fromWkt("LINESTRING Z (13 46 200, 14 47 300)"))
    assert other.dataProvider().addFeatures([feature])[0]
    QgsProject.instance().addMapLayer(other)
    wait_until("document.querySelector('#layer').options.length === 2")
    evaluate("""
        (() => { const select = document.querySelector('#layer');
          select.value = %s; select.dispatchEvent(new Event('change')); return true; })()
    """ % json.dumps(other.id()))
    wait_until("document.querySelector('[data-action=html]').disabled")
    wait_until("!document.querySelector('[data-action=html]').disabled")
    assert context.dialog.layer_combo.currentLayer() == other
    assert json.loads(context.dialog.opts["elevationControl"]["data"])["name"] == "Other track"

    path = str(Path(context.tempdir.name) / "track.html")
    with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "*.html")):
        evaluate("document.querySelector('[data-action=html]').click(); true")
        wait_until("document.querySelector('#layer').value !== ''")
    assert Path(path).exists(), "exported file"
    html = Path(path).read_text(encoding="utf-8")
    assert "settings-panel" not in html and "qwebchannel" not in html and "#00ff00" in html
    evaluate("""(() => {
      const input = document.querySelector('#profileWidth');
      input.value = '11'; input.dispatchEvent(new Event('change')); return true;
    })()""")
    wait_until("document.querySelector('[data-action=html]').disabled")
    assert context.dialog.settings["profileWidth"] == 4
    evaluate("""(() => {
      const input = document.querySelector('#profileWidth');
      input.value = '4'; input.dispatchEvent(new Event('change')); return true;
    })()""")
    wait_until("!document.querySelector('[data-action=html]').disabled")
    invalid = dict(context.dialog.settings, profileColor="red; }")
    with patch.object(context.dialog.bar, "pushMessage") as message:
        context.dialog.bridge.setOptions(json.dumps(invalid))
        message.assert_called_once()
    assert context.dialog.settings["profileColor"] == "#00ff00"
    evaluate("""(() => {
      const input = document.querySelector('#basemap');
      input.value = 'https://example.test/{z}/{x}/{y}.png';
      input.dispatchEvent(new Event('change')); return true;
    })()""")
    wait_until("document.querySelector('[data-action=html]').disabled")
    wait_until("!document.querySelector('[data-action=html]').disabled")
    assert context.dialog.opts["otmLayer"]["url"] == "https://example.test/{z}/{x}/{y}.png"
    assert context.dialog.opts["otmLayer"]["options"]["attribution"] == ""


@then("the preview follows option and layer changes without refetching unchanged elevations")
def check_automatic_preview(context):
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from qgis.PyQt.QtGui import QColor
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, QgsVectorLayer

    def wait_for_preview():
        loop = QEventLoop()
        QTimer.singleShot(500, loop.quit)
        loop.exec()

    def javascript(script):
        result = []
        loop = QEventLoop()
        context.dialog.mapview.page().runJavaScript(
            script, lambda value: (result.append(value), loop.quit())
        )
        QTimer.singleShot(5000, loop.quit)
        loop.exec()
        assert result, "The HTML interface did not respond"
        return result[0]

    module = importlib.import_module(ROOT.name + ".track_profile_2_web")
    with patch.object(
        module, "_fetch_mapterhorn_tile",
        side_effect=lambda zoom, x, y: context.mapterhorn_image if zoom == 13 else None
    ), patch.object(
        module, "_layer_with_mapterhorn_elevations",
        wraps=module._layer_with_mapterhorn_elevations
    ) as drape:
        context.dialog.show()
        wait_for_preview()
        assert drape.call_count == 1
        assert context.dialog._preview_status == "ready"

        javascript("""(() => {
          for (const [id, value] of [['basemap', 'OpenStreetMap'], ['profileColor', '#00ff00']]) {
            const input = document.getElementById(id);
            input.value = value; input.dispatchEvent(new Event('change'));
          }
          return true;
        })()""")
        wait_for_preview()
        assert drape.call_count == 1
        assert context.dialog.opts["otmLayer"]["url"] == "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        assert "#00ff00" in Path(context.dialog.fout).read_text(encoding="utf-8")
        assert context.dialog._preview_status == "ready"

        feature = next(context.layer.getFeatures())
        assert context.layer.startEditing()
        assert context.layer.changeGeometry(
            feature.id(), QgsGeometry.fromWkt("LINESTRING (12 45, 12.02 45.02)")
        )
        wait_for_preview()
        assert drape.call_count == 2
        data = json.loads(context.dialog.opts["elevationControl"]["data"])
        assert data["features"][0]["geometry"]["coordinates"][-1] == [12.02, 45.02, 100]

        context.mapterhorn_image = None
        assert context.layer.changeGeometry(
            feature.id(), QgsGeometry.fromWkt("LINESTRING (12 45, 12.03 45.03)")
        )
        wait_for_preview()
        assert drape.call_count == 3
        assert context.dialog._preview_status == "error"
        assert context.dialog._preview_url == ""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if javascript("""(() => {
              const retry = document.querySelector('#retry');
              const notice = document.querySelector('#notice');
              return retry && !retry.hidden && notice.textContent.includes('Could not get elevations');
            })()"""):
                break
            loop = QEventLoop()
            QTimer.singleShot(150, loop.quit)
            loop.exec()
        else:
            raise AssertionError("The retry button and error message did not appear")
        from qgis.PyQt.QtGui import QImage
        context.mapterhorn_image = QImage(512, 512, QImage.Format.Format_RGB32)
        context.mapterhorn_image.fill(QColor(128, 100, 0))
        javascript("document.querySelector('#retry').click(); true")
        wait_for_preview()
        assert drape.call_count == 4
        assert context.dialog._preview_status == "ready"

        other = QgsVectorLayer("LineStringZ?crs=EPSG:4326", "Other track", "memory")
        feature = QgsFeature(other.fields())
        feature.setGeometry(QgsGeometry.fromWkt("LINESTRING Z (13 46 200, 14 47 300)"))
        assert other.dataProvider().addFeatures([feature])[0]
        QgsProject.instance().addMapLayer(other)
        context.dialog.layer_combo.setLayer(other)
        wait_for_preview()
        assert drape.call_count == 4
        data = json.loads(context.dialog.opts["elevationControl"]["data"])
        assert data["features"][0]["geometry"]["coordinates"][0] == [13, 46, 200]

        QgsProject.instance().removeMapLayer(context.layer.id())
        QgsProject.instance().removeMapLayer(other.id())
        wait_for_preview()
        assert context.dialog._preview_status == "empty"


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


@then("the plugin opens the dialog maximized each time")
def check_maximized_dialog(context):
    from qgis.PyQt.QtCore import QTimer
    from qgis.PyQt.QtWidgets import QApplication

    iface = MagicMock()
    iface.mainWindow.return_value = None
    plugin = importlib.import_module(ROOT.name).classFactory(iface)
    plugin.initGui()
    states = []

    def close_dialog():
        states.append(plugin.dlg.isMaximized())
        plugin.dlg.reject()

    app = QApplication.instance()
    quit_on_close = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)
    try:
        for _ in range(2):
            QTimer.singleShot(100, close_dialog)
            plugin.run()
            plugin.dlg.showNormal()
    finally:
        if hasattr(plugin, "dlg"):
            plugin.dlg.hide()
            plugin.dlg.preview_dir.cleanup()
        app.setQuitOnLastWindowClosed(quit_on_close)
    assert states == [True, True]


@then("the preview contains the line coordinates and elevations")
def check_preview(context):
    data = json.loads(context.dialog.opts["elevationControl"]["data"])
    assert data["features"][0]["geometry"]["coordinates"] == COORDINATES
    assert Path(context.dialog.fout).is_file()


@then("the export buttons are enabled")
def exports_enabled(context):
    assert context.dialog._preview_status == "ready"


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
            """(() => { const frame = document.querySelector('#preview'); const doc = frame?.contentDocument; return JSON.stringify({ready: doc?.readyState, value: doc?.querySelector('.maxele .summaryvalue')?.textContent, url: frame?.src}); })()""", finish
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
    assert context.dialog._preview_status != "ready"


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
    assert "settings-panel" not in html and "qwebchannel" not in html
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
    before, preview = html.split('<template id="qgis-preview">', 1)
    _, after = preview.split('</template>', 1)
    html = before + after
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
    for width, height in ((900, 560), (900, 400), (900, 800), (320, 560)):
        context.page.set_viewport_size({"width": width, "height": height})
        context.page.wait_for_timeout(200)
        assert context.page.evaluate("""
            () => {
              const doc = document.documentElement;
              const summary = document.querySelector('#data-summary').getBoundingClientRect();
              const chart = document.querySelector('.elevation-control svg.background').getBoundingClientRect();
              return doc.scrollWidth <= doc.clientWidth && doc.scrollHeight <= doc.clientHeight
                && chart.bottom <= innerHeight && summary.bottom <= innerHeight
                && (document.body.classList.contains('attached-profile') || chart.bottom <= summary.top);
            }
        """), "chart and summary must fit in the viewport"


@then("the profile is attached to the map")
def check_attached(context):
    assert context.page.locator("#map .custom-theme.elevation-control").count() == 1
    assert context.page.locator("#map").evaluate(
        "element => element.getBoundingClientRect().height === window.innerHeight"
    )
