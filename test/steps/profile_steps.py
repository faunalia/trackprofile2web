import json
import importlib
import struct
import threading
import time
import zlib
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
    context.dialog.show()
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
        && !document.querySelector('#panel-toggle, #panel-close')
        && [...document.querySelectorAll('[data-action]')].map(button => button.dataset.action).join(',') === 'export';
    })()"""), "settings must be visible without toggle controls at startup"
    wait_until("document.querySelector('#layer')?.value && !document.querySelector('[data-action=export]')?.disabled")
    wait_until("!!document.querySelector('#preview')?.contentDocument?.querySelector('.lightblue-theme.elevation-control')")
    assert evaluate("""(() => document.getElementById('theme').value === 'lightblue-theme'
      && !document.getElementById('advanced-options').open
      && document.getElementById('custom-appearance').hidden)()"""), "default theme and collapsed advanced options"
    assert evaluate("document.querySelector('#layer').selectedOptions[0].textContent") == "Test track", "layer"
    assert evaluate("document.querySelector('#preview').src.includes('map.html')"), "preview URL"
    assert evaluate("document.querySelector('#preview').getBoundingClientRect().height === innerHeight"), "preview height"
    wait_until("!!document.querySelector('#preview').contentWindow.controlLayer")
    assert evaluate("""(() => {
      const frame = document.querySelector('#preview').getBoundingClientRect();
      const panel = document.querySelector('#settings-panel').getBoundingClientRect();
      return panel.left === frame.right && panel.right === innerWidth
        && panel.top === 0 && panel.bottom === innerHeight && frame.width > 0;
    })()"""), "settings must occupy a separate full-height right sidebar"
    assert evaluate("""(() => {
      const panel = document.querySelector('#settings-panel');
      const content = panel.querySelector('.content');
      const advanced = document.querySelector('#advanced-options');
      advanced.open = true;
      advanced.querySelectorAll('details').forEach(section => section.open = true);
      const footer = panel.querySelector('.export-footer').getBoundingClientRect();
      const bottom = panel.getBoundingClientRect().bottom;
      const visible = content.scrollHeight > content.clientHeight
        && Math.abs(footer.bottom - bottom) < 1
        && document.querySelector('#export-button').getClientRects().length > 0;
      advanced.querySelectorAll('details').forEach(section => section.open = false);
      advanced.open = false;
      return visible;
    })()"""), "export button must remain visible with advanced options expanded"
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
            ['basemap', 'OpenStreetMap'], ['theme', 'custom-theme'],
            ['profileColor', '#00ff00'],
            ['lineColor', '#0033ff'], ['markerColor', '#ff00ff'],
            ['profileWidth', '4'], ['markerOpacity', '0.5'], ['position', 'bottomleft'],
            ['interpolation', 'curveStep'], ['yAxisMin', '0'], ['yAxisMax', '500'],
            ['marker', 'position-marker'], ['dragging', 'disabled'], ['zooming', 'enabled'],
            ['xTicks', '8'], ['yTicks', '6'], ['decimalsX', '1'], ['decimalsY', '2'], ['zFollow', '14']
          ]) {
            const input = document.getElementById(id);
            input.value = value;
            input.dispatchEvent(new Event('change'));
          }
          for (const [id, value] of [
            ['detached', false], ['follow', true], ['collapseProfile', true],
            ['autohide', true], ['collapseLayers', true], ['slope', true],
            ['imperial', true], ['trackEndpoints', false], ['rotateMap', true],
            ['autohideMarker', false]
          ]) {
            const input = document.getElementById(id);
            input.checked = value;
            input.dispatchEvent(new Event('change'));
          }
          return true;
        })()
    """)
    wait_until("document.querySelector('[data-action=export]').disabled")
    wait_until("!document.querySelector('[data-action=export]').disabled")
    assert evaluate("""(() => !document.getElementById('custom-appearance').hidden
      && !document.getElementById('advanced-options').open)()"""), "custom controls should follow the theme selection"
    assert context.dialog.settings["basemap"] == "OpenStreetMap", "basemap"
    assert context.dialog.settings["theme"] == "custom-theme"
    assert context.dialog.settings["profileColor"] == "#00ff00", "profile color"
    assert "#00ff00" in Path(context.dialog.fout).read_text(encoding="utf-8"), "generated preview color"
    assert context.dialog.settings["lineColor"] == "#0033ff"
    assert context.dialog.settings["markerColor"] == "#ff00ff"
    assert context.dialog.settings["profileWidth"] == 4
    assert context.dialog.settings["markerOpacity"] == 0.5
    assert context.dialog.settings["slope"] and context.dialog.settings["imperial"]
    assert context.dialog.settings["interpolation"] == "curveStep"
    assert context.dialog.settings["yAxisMin"] == 0
    assert context.dialog.settings["yAxisMax"] == 500
    assert context.dialog.settings["marker"] == "position-marker"
    assert context.dialog.settings["dragging"] == "disabled"
    assert context.dialog.settings["zooming"] == "enabled"
    assert context.dialog.settings["xTicks"] == 8 and context.dialog.settings["yTicks"] == 6
    assert context.dialog.settings["decimalsX"] == 1 and context.dialog.settings["decimalsY"] == 2
    assert context.dialog.settings["zFollow"] == 14 and context.dialog.settings["rotateMap"]
    wait_until("""(() => {
      const frame = document.querySelector('#preview');
      const options = frame.contentWindow.controlElevation?.options;
      return options?.position === 'bottomleft' && options.theme === 'custom-theme'
        && !options.detached && options.followMarker
        && options.autohide && options.collapsed
        && options.slope && options.imperial
        && options.interpolation === 'curveStep'
        && options.yAxisMax === 500
        && options.trkStart === false
        && frame.contentWindow.controlLayer?.options.collapsed
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
      return frame.contentWindow.controlElevation?.options.detached
        && !!frame.contentDocument.querySelector('#elevation-div svg.background')
        && !!frame.contentDocument.querySelector('.custom-theme.elevation-control .area path.altitude')
        && !document.querySelector('#settings-panel').hidden
        && !frame.contentDocument.querySelector('[aria-label="Settings & export"]');
    })()""")
    assert evaluate("""(() => {
      const frame = document.querySelector('#preview');
      const doc = frame.contentDocument;
      const chart = doc.querySelector('#elevation-div svg.background').getBoundingClientRect();
      const summary = doc.querySelector('#data-summary').getBoundingClientRect();
      const area = frame.contentWindow.getComputedStyle(doc.querySelector('.custom-theme.elevation-control .area path.altitude'));
      return chart.right <= frame.clientWidth && chart.bottom <= summary.top
        && doc.documentElement.scrollWidth <= doc.documentElement.clientWidth
        && doc.documentElement.scrollHeight <= doc.documentElement.clientHeight
        && area.fill === 'rgb(0, 255, 0)' && area.strokeWidth === '4px';
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
    wait_until("document.querySelector('[data-action=export]').disabled")
    wait_until("!document.querySelector('[data-action=export]').disabled")
    assert context.dialog.layer_combo.currentLayer() == other
    assert json.loads(context.dialog.config["data"])["name"] == "Other track"

    module = importlib.import_module(ROOT.name + ".track_profile_2_web")
    with patch.object(module.QtWidgets.QMessageBox, "question",
                      return_value=module.QtWidgets.QMessageBox.StandardButton.No), \
         patch.object(module.QDesktopServices, "openUrl") as open_url:
        evaluate("""(() => {
          const input = document.querySelector('#terrain3D');
          input.checked = true; input.dispatchEvent(new Event('change')); return true;
        })()""")
        wait_until("!document.querySelector('#terrain3D').checked")
        assert not context.dialog.settings["terrain3D"]
        open_url.assert_not_called()
    path = str(Path(context.tempdir.name) / "track.html")
    with patch.object(QFileDialog, "getSaveFileName", return_value=(path, "*.html")):
        evaluate("document.querySelector('#export-button').click(); true")
        wait_until("document.querySelector('#export-dialog').open")
        evaluate("document.querySelector('#export-dialog button[value=export]').click(); true")
        deadline = time.monotonic() + 15
        while not Path(path).exists() and time.monotonic() < deadline:
            loop = QEventLoop()
            QTimer.singleShot(100, loop.quit)
            loop.exec()
    assert Path(path).exists(), "exported file"
    html = Path(path).read_text(encoding="utf-8")
    assert "settings-panel" not in html and "qwebchannel" not in html and "#00ff00" in html
    assert '"slope": true' in html and '"imperial": true' in html
    assert '"terrain3D": false' in html and '"rotateMap": true' in html
    geojson = Path(context.tempdir.name) / "Other-track.geojson"
    with patch.object(QFileDialog, "getExistingDirectory", return_value=context.tempdir.name):
        evaluate("document.querySelector('#export-button').click(); true")
        wait_until("document.querySelector('#export-dialog').open")
        evaluate("""(() => {
          const dialog = document.querySelector('#export-dialog');
          dialog.querySelector('[name=export-format][value=geojson]').checked = true;
          dialog.querySelector('button[value=export]').click();
          return true;
        })()""")
        deadline = time.monotonic() + 15
        while not geojson.exists() and time.monotonic() < deadline:
            loop = QEventLoop()
            QTimer.singleShot(100, loop.quit)
            loop.exec()
    assert geojson.exists(), "HTML + GeoJSON export choice"
    evaluate("""(() => {
      const input = document.querySelector('#profileWidth');
      input.value = '11'; input.dispatchEvent(new Event('change')); return true;
    })()""")
    wait_until("document.querySelector('[data-action=export]').disabled")
    assert context.dialog.settings["profileWidth"] == 4
    evaluate("""(() => {
      const input = document.querySelector('#profileWidth');
      input.value = '4'; input.dispatchEvent(new Event('change')); return true;
    })()""")
    wait_until("!document.querySelector('[data-action=export]').disabled")
    evaluate("""(() => {
      const input = document.querySelector('#yAxisMax');
      input.value = '0'; input.dispatchEvent(new Event('change')); return true;
    })()""")
    wait_until("document.querySelector('[data-action=export]').disabled")
    assert context.dialog.settings["yAxisMax"] == 500
    evaluate("""(() => {
      const input = document.querySelector('#yAxisMax');
      input.value = '500'; input.dispatchEvent(new Event('change')); return true;
    })()""")
    wait_until("!document.querySelector('[data-action=export]').disabled")
    invalid = dict(context.dialog.settings, profileColor="red; }")
    with patch.object(context.dialog.bar, "pushMessage") as message:
        context.dialog.bridge.setOptions(json.dumps(invalid))
        message.assert_called_once()
    assert context.dialog.settings["profileColor"] == "#00ff00"
    invalid = dict(context.dialog.settings, theme="unknown-theme")
    with patch.object(context.dialog.bar, "pushMessage") as message:
        context.dialog.bridge.setOptions(json.dumps(invalid))
        message.assert_called_once()
    assert context.dialog.settings["theme"] == "custom-theme"
    invalid = dict(context.dialog.settings, yAxisMin=600, yAxisMax=500)
    with patch.object(context.dialog.bar, "pushMessage") as message:
        context.dialog.bridge.setOptions(json.dumps(invalid))
        message.assert_called_once()
    assert context.dialog.settings["yAxisMax"] == 500
    evaluate("""(() => {
      const input = document.querySelector('#basemap');
      input.value = 'https://example.test/{z}/{x}/{y}.png';
      input.dispatchEvent(new Event('change')); return true;
    })()""")
    wait_until("document.querySelector('[data-action=export]').disabled")
    wait_until("!document.querySelector('[data-action=export]').disabled")
    assert context.dialog.config["settings"]["basemapUrl"] == "https://example.test/{z}/{x}/{y}.png"
    assert context.dialog.config["settings"]["basemapAttribution"] == ""
    wait_until("""(() => {
      const frame = document.querySelector('#preview');
      return frame.contentDocument.readyState === 'complete'
        && frame.contentWindow.baseLayers?.OTM._url === 'https://example.test/{z}/{x}/{y}.png';
    })()""")
    with patch.object(module.QtWidgets.QMessageBox, "question",
                      return_value=module.QtWidgets.QMessageBox.StandardButton.Yes), \
         patch.object(module.QDesktopServices, "openUrl", return_value=True):
        evaluate("""(() => {
          const input = document.querySelector('#terrain3D');
          input.checked = true; input.dispatchEvent(new Event('change')); return true;
        })()""")
        wait_until("document.querySelector('[data-action=export]').disabled")
        wait_until("!document.querySelector('[data-action=export]').disabled")
    assert context.dialog.settings["terrain3D"]
    path_3d = str(Path(context.tempdir.name) / "track-3d.html")
    with patch.object(QFileDialog, "getSaveFileName", return_value=(path_3d, "*.html")):
        context.dialog.saveAsHtml()
    assert '"terrain3D": true' in Path(path_3d).read_text(encoding="utf-8")
    context.dialog.mapview.reload()
    wait_until("""document.querySelector('#terrain3D')?.checked
      && document.querySelector('#profileColor')?.value === '#00ff00'
      && !document.querySelector('[data-action=export]')?.disabled""")


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
        context.dialog._schedule_preview()
        wait_for_preview()
        assert drape.call_count == 1
        assert context.dialog._preview_status == "ready"

        javascript("""(() => {
          for (const [id, value] of [
            ['basemap', 'OpenStreetMap'], ['theme', 'custom-theme'], ['profileColor', '#00ff00']
          ]) {
            const input = document.getElementById(id);
            input.value = value; input.dispatchEvent(new Event('change'));
          }
          return true;
        })()""")
        wait_for_preview()
        assert drape.call_count == 1
        assert context.dialog.config["settings"]["basemapUrl"] == "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        assert "#00ff00" in Path(context.dialog.fout).read_text(encoding="utf-8")
        assert context.dialog._preview_status == "ready"

        feature = next(context.layer.getFeatures())
        assert context.layer.startEditing()
        assert context.layer.changeGeometry(
            feature.id(), QgsGeometry.fromWkt("LINESTRING (12 45, 12.02 45.02)")
        )
        wait_for_preview()
        assert drape.call_count == 2
        data = json.loads(context.dialog.config["data"])
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
        data = json.loads(context.dialog.config["data"])
        assert data["features"][0]["geometry"]["coordinates"][0] == [13, 46, 200]

        QgsProject.instance().removeMapLayer(context.layer.id())
        QgsProject.instance().removeMapLayer(other.id())
        wait_for_preview()
        assert context.dialog._preview_status == "empty"


@then("the preview contains the Mapterhorn elevations")
def check_mapterhorn_preview(context):
    data = json.loads(context.dialog.config["data"])
    assert data["features"][0]["geometry"]["coordinates"] == [
        [12.0, 45.0, 100.0],
        [12.01, 45.01, 100.0],
    ]


@then("the original layer remains 2D")
def check_source_layer_is_unchanged(context):
    from qgis.core import QgsWkbTypes

    assert not QgsWkbTypes.hasZ(context.layer.wkbType())
    assert QgsWkbTypes.hasZ(context.dialog.vlayer.wkbType())
    assert "Mapterhorn" in context.dialog.config["settings"]["basemapAttribution"]


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


@then("the plugin opens the QGIS dialog each time")
def check_dialog_launch(context):
    iface = MagicMock()
    iface.mainWindow.return_value = None
    plugin = importlib.import_module(ROOT.name).classFactory(iface)
    plugin.initGui()
    module = importlib.import_module(ROOT.name + ".track_profile_2_web")
    with patch.object(module.QDesktopServices, "openUrl", return_value=True) as open_url:
        for _ in range(2):
            plugin.run()
            assert plugin.dlg.isVisible() and plugin.dlg.isMaximized()
            plugin.dlg.hide()
        open_url.assert_not_called()
    plugin.unload()


@then("3D preview requires confirmation and returns to QGIS for 2D")
def check_3d_preview_switch(context):
    from qgis.PyQt.QtCore import QEventLoop, QTimer, QUrl
    from qgis.PyQt.QtWebEngineWidgets import QWebEngineView

    def wait_for_script(view, script):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            results = []
            loop = QEventLoop()
            view.page().runJavaScript(script, lambda value: (results.append(value), loop.quit()))
            QTimer.singleShot(1000, loop.quit)
            loop.exec()
            if results and results[0]:
                return
            loop = QEventLoop()
            QTimer.singleShot(100, loop.quit)
            loop.exec()
        raise AssertionError("Browser interface did not reach expected state: " + script)

    module = importlib.import_module(ROOT.name + ".track_profile_2_web")
    settings = dict(context.dialog.settings)
    settings["terrain3D"] = True
    buttons = module.QtWidgets.QMessageBox.StandardButton
    with patch.object(module.QtWidgets.QMessageBox, "question", return_value=buttons.No), \
         patch.object(module.QDesktopServices, "openUrl", return_value=True) as open_url:
        context.dialog.bridge.setOptions(json.dumps(settings))
        assert not context.dialog.settings["terrain3D"]
        open_url.assert_not_called()
    with patch.object(module.QtWidgets.QMessageBox, "question", return_value=buttons.Yes), \
         patch.object(module.QDesktopServices, "openUrl", return_value=False):
        context.dialog.bridge.setOptions(json.dumps(settings))
        assert not context.dialog.settings["terrain3D"]
        assert context.dialog.bar.currentItem() is not None
    with patch.object(module.QtWidgets.QMessageBox, "question", return_value=buttons.Yes), \
         patch.object(module.QDesktopServices, "openUrl", return_value=True) as open_url:
        context.dialog.bridge.setOptions(json.dumps(settings))
        assert context.dialog.settings["terrain3D"] and not context.dialog.isVisible()
        assert open_url.call_args.args[0].toString() == context.dialog.server.base_url
    browser = QWebEngineView()
    try:
        browser.setUrl(QUrl(context.dialog.server.base_url))
        wait_for_script(browser, "document.querySelector('#terrain3D')?.checked && document.querySelector('#inactive')?.hidden")
        wait_for_script(browser, """(() => {
          const input = document.querySelector('#terrain3D');
          input.checked = false; input.dispatchEvent(new Event('change')); return true;
        })()""")
        wait_for_script(browser, "document.querySelector('#inactive') && !document.querySelector('#inactive').hidden")
        assert not context.dialog.settings["terrain3D"] and context.dialog.isVisible()
        wait_for_script(context.dialog.mapview, "document.querySelector('#terrain3D') && !document.querySelector('#terrain3D').checked")
    finally:
        browser.close()
        browser.deleteLater()


@then("the preview server rejects unauthorized requests")
def check_preview_server(context):
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    from qgis.PyQt.QtCore import QEventLoop, QTimer

    server = context.dialog.server
    results = []
    def request(url, headers=None, data=None):
        try:
            with urlopen(Request(url, headers=headers or {}, data=data), timeout=5) as response:
                return response.status
        except HTTPError as error:
            return error.code
    def probe():
        results.extend([
            request(server.base_url + "state"),
            request(server.origin + "/wrong/state"),
            request(server.base_url + "state", headers={"Host": "attacker.example"}),
            request(server.base_url + "command", headers={"Origin": "https://attacker.example"},
                    data=b'{"name":"retry"}'),
        ])
    thread = threading.Thread(target=probe)
    thread.start()
    deadline = time.monotonic() + 10
    while thread.is_alive() and time.monotonic() < deadline:
        loop = QEventLoop()
        QTimer.singleShot(50, loop.quit)
        loop.exec()
    thread.join(timeout=1)
    assert results == [200, 404, 403, 404], results


@then("the preview contains the line coordinates and elevations")
def check_preview(context):
    data = json.loads(context.dialog.config["data"])
    assert data["features"][0]["geometry"]["coordinates"] == COORDINATES
    assert Path(context.dialog.fout).is_file()


@then("the export button is enabled")
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


@then("the export button remains disabled")
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
    assert json.loads(context.dialog.config["data"])["type"] == "FeatureCollection"


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
    preview = json.loads(context.dialog.config["data"])
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


def prepare_web_profile(context, separate, detached=True, overrides=None):
    data = {
        "type": "FeatureCollection",
        "name": "Test track",
        "features": [{"type": "Feature", "properties": {},
                      "geometry": {"type": "LineString", "coordinates": COORDINATES}}],
    }
    folder = Path(context.tempdir.name)
    if separate:
        (folder / "track.geojson").write_text(json.dumps(data), encoding="utf-8")
    config = {
        "data": "track.geojson" if separate else json.dumps(data),
        "settings": {
            "basemapUrl": "", "basemapAttribution": "Test basemap attribution",
            "position": "topright", "theme": "custom-theme", "detached": detached, "follow": False,
            "autohide": False, "collapseProfile": False, "collapseLayers": True,
            "profileColor": "#00ff00", "profileWidth": 4,
            "markerColor": "#ff00ff", "lineColor": "#0033ff", "markerOpacity": 0.5,
            "slope": False, "imperial": False, "distanceMarkers": False, "hotline": False,
            "legend": True, "ruler": True, "trackEndpoints": True, "edgeScale": False,
            "autofitBounds": True, "interpolation": "curveLinear",
            "rotateMap": False, "terrain3D": False, "autohideMarker": True,
            "marker": "elevation-line", "dragging": "auto", "zooming": "auto",
            "xTicks": None, "yTicks": None, "decimalsX": None, "decimalsY": None,
            "zFollow": None,
            "width": None, "height": None, "xAxisMin": None, "xAxisMax": None,
            "yAxisMin": None, "yAxisMax": None,
        },
    }
    if overrides:
        config["settings"].update(overrides)
    html = (ROOT / "track_profile_2_web.html").read_text(encoding="utf-8")
    before, preview = html.split('<template id="qgis-preview">', 1)
    _, after = preview.split('</template>', 1)
    html = before + after
    html = html.replace("'{ py_opts }'", json.dumps(config))
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


@given("an elevation profile with customized chart and track options")
def customized_profile(context):
    prepare_web_profile(context, False, overrides={
        "slope": True, "imperial": True, "distanceMarkers": True, "hotline": True,
        "legend": False, "ruler": False, "trackEndpoints": False, "edgeScale": True,
        "autofitBounds": False, "interpolation": "curveStep", "width": 500, "height": 200,
        "xAxisMin": 0, "xAxisMax": 2, "yAxisMin": 0, "yAxisMax": 1000,
        "rotateMap": True, "autohideMarker": False, "marker": "position-marker",
        "dragging": "disabled", "zooming": "enabled", "xTicks": 8, "yTicks": 6,
        "decimalsX": 1, "decimalsY": 2, "zFollow": 14,
    })


@given("an elevation profile with 3D terrain")
def terrain_profile(context, rotation=True):
    prepare_web_profile(context, False, overrides={
        "terrain3D": True, "rotateMap": rotation, "distanceMarkers": True, "hotline": True,
        "basemapUrl": "https://example.test/tiles/{z}/{x}/{y}.png",
    })
    path = Path(context.tempdir.name) / "profile.html"
    html = path.read_text(encoding="utf-8").replace(
        "async getTile(z, x, y, signal) {",
        "getTile: window.testTerrainTile = async function(z, x, y, signal) {",
    ).replace(
        "terrainLayer.addTo(map);",
        "map.on('terrainchange', () => window.terrainChanges = (window.terrainChanges || 0) + 1);"
        "terrainLayer.addTo(map);",
    )
    path.write_text(html, encoding="utf-8")
    context.terrain_profile = True


@given("an elevation profile with 3D terrain and rotation disabled")
def terrain_without_rotation(context):
    terrain_profile(context, rotation=False)


@given("an elevation profile with 3D terrain but no WebGPU")
def terrain_without_gpu(context):
    prepare_web_profile(context, False, overrides={"terrain3D": True, "rotateMap": True})
    context.no_gpu = True


@given("an elevation profile with 3D terrain and unavailable elevation tiles")
def terrain_with_missing_tiles(context):
    terrain_profile(context)
    context.missing_terrain = True


@given("an elevation profile with an unavailable rotation library")
def profile_with_missing_rotation(context):
    prepare_web_profile(context, False, overrides={"rotateMap": True})
    context.missing_rotation = True


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
    if getattr(context, "no_gpu", False):
        context.page.add_init_script("Object.defineProperty(navigator, 'gpu', {value: undefined})")
    if getattr(context, "missing_rotation", False):
        context.page.route("https://unpkg.com/leaflet-rotate@*/dist/leaflet-rotate.js",
                           lambda route: route.abort())
    if getattr(context, "terrain_profile", False):
        def chunk(name, data):
            payload = name + data
            return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload))
        pixels = (b"\x00" + b"\x80\x64\x00\xff" * 256 + b"\x81\x64\x00\xff" * 256) * 512
        image = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 512, 512, 8, 6, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))
        context.terrain_requests = []
        def serve_terrain(route):
            context.terrain_requests.append(route.request.url)
            if getattr(context, "missing_terrain", False):
                route.fulfill(status=500)
            else:
                route.fulfill(status=200, content_type="image/png", body=image)
        context.page.route("https://tiles.mapterhorn.com/**", serve_terrain)
        context.page.route("https://example.test/tiles/**", lambda route: route.fulfill(
            status=200, content_type="image/png", body=image,
            headers={"Access-Control-Allow-Origin": "*"}
        ))
    context.page.goto("http://127.0.0.1:{}/profile.html".format(context.server.server_port))


@when("I open the profile as a local file")
def open_local_profile(context):
    open_profile(context)
    context.page.goto((Path(context.tempdir.name) / "profile.html").as_uri())


@then("the chart and its elevation summary are displayed")
def check_chart(context):
    context.page.wait_for_function(
        "document.querySelector('.maxele .summaryvalue').textContent === '200.00 m'",
        timeout=30000
    )
    assert context.page.locator(".custom-theme.elevation-control .area path.altitude").count() > 0
    assert not context.page.evaluate("""() => performance.getEntriesByType('resource').some(
      entry => entry.name.includes('leaflet-city-mapper') || entry.name.includes('leaflet-rotate'))""")
    assert context.page.locator(".minele .summaryvalue").inner_text() == "100.00 m"
    assert context.page.locator(".custom-theme.elevation-control .area path.altitude").first.evaluate(
        "element => getComputedStyle(element).fill === 'rgb(0, 255, 0)' && getComputedStyle(element).strokeWidth === '4px'"
    )
    assert context.page.evaluate("""() => {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.innerHTML = '<path class="custom-theme elevation-polyline"></path>' +
        '<circle class="custom-theme height-focus circle-lower"></circle>';
      document.body.appendChild(svg);
      const line = getComputedStyle(svg.querySelector('path'));
      const marker = getComputedStyle(svg.querySelector('circle'));
      const matches = line.stroke === 'rgb(0, 51, 255)' && line.strokeOpacity === '0.5'
        && marker.fill === 'rgb(255, 0, 255)';
      svg.remove();
      return matches;
    }""")
    attribution = context.page.locator(".leaflet-control-attribution")
    assert "Test basemap attribution" in attribution.inner_text()
    assert attribution.get_by_role("link", name="Raruto").get_attribute("href") == "https://raruto.github.io"
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


@then("the customized options and imperial summary are displayed")
def check_customized_profile(context):
    page = context.page
    page.wait_for_function("document.querySelector('.maxele .summaryvalue').textContent.endsWith(' ft')", timeout=30000)
    page.wait_for_function("""() => map.edgeScaleControl && controlElevation._hotline.getLayers().length
      && document.querySelector('.custom-theme.elevation-polyline')""", timeout=30000)
    page.evaluate("() => map.setView([45.005, 12.005], 13)")
    page.wait_for_function("""() => {
      const line = controlElevation._layers.getLayers().find(layer => layer instanceof L.Polyline);
      return line && line._distanceMarkers && line._distanceMarkers.getLayers().length;
    }""", timeout=30000)
    assert page.locator(".maxele .summaryvalue").inner_text() == "656.17 ft"
    assert page.locator(".minele .summaryvalue").inner_text() == "328.08 ft"
    assert page.locator(".totlen .summaryvalue").inner_text().endswith(" mi")
    assert page.locator(".ascent .summaryvalue").inner_text() == "328.08 ft"
    assert page.locator(".descent .summaryvalue").inner_text() == "0.00 ft"
    assert page.locator(".area path.slope").count() > 0
    assert page.evaluate("""() => {
      const c = controlElevation, o = c.options, point = c._data[1];
      const meters = c._data[0].latlng.distanceTo(point.latlng);
      const line = c._layers.getLayers().find(layer => layer instanceof L.Polyline);
      const arrow = line._distanceMarkers.getLayers().flatMap(group => group.getLayers())
        .find(marker => marker.options.rotation);
      return Math.abs(point.slope - 10000 / meters) < 0.05
        && o.distanceMarkers.offset === 804.672 && o.distanceMarkers.textFunction(1609.344) === '1'
        && arrow && arrow._icon.style.transform.includes('rotate')
        && o.hotline === 'elevation' && o.edgeScale
        && !o.legend && !o.ruler && !o.trkStart && !o.trkEnd && !o.autofitBounds
        && o.interpolation === 'curveStep' && o.height === 200
        && !o.autohideMarker && o.marker === 'position-marker' && !o.dragging && o.zooming
        && o.xTicks === 8 && o.yTicks === 6 && o.decimalsX === 1 && o.decimalsY === 2 && o.zFollow === 14
        && map.options.rotateControl && map.options.shiftKeyRotate
        && o.xAxisMin === 0 && o.xAxisMax === 2 && o.yAxisMin === 0 && o.yAxisMax === 1000
        && c._chart._scales.distance.domain().join(',') === '0,2'
        && c._chart._scales.altitude.domain().join(',') === '0,1000'
        && document.querySelector('#elevation-div').getBoundingClientRect().width === 500
        && document.querySelector('#elevation-div svg.background').getBoundingClientRect().height === 200
        && getComputedStyle(document.querySelector('.custom-theme.elevation-polyline')).strokeOpacity === '0';
    }""")


@then("the map displays 3D terrain and the elevation profile")
def check_terrain(context):
    page = context.page
    if not page.evaluate("async () => !!(await navigator.gpu?.requestAdapter())"):
        context.scenario.skip("WebGPU is unavailable in this browser")
        return
    page.wait_for_selector("canvas.leaflet-3d", timeout=30000)
    page.wait_for_function("document.querySelector('.maxele .summaryvalue').textContent === '200.00 m'", timeout=30000)
    page.wait_for_function("!document.querySelector('#map-warning').offsetWidth", timeout=30000)
    deadline = time.monotonic() + 30
    while not context.terrain_requests and time.monotonic() < deadline:
        page.wait_for_timeout(200)
    assert context.terrain_requests, "the 3D map must request terrain tiles"
    page.wait_for_function("window.terrainChanges > 1", timeout=30000)
    page.wait_for_function("""() => controlElevation._hotline.getLayers().length &&
      controlElevation._layers.getLayers().some(layer => layer instanceof L.Polyline)""", timeout=30000)
    result = page.evaluate("""async () => {
      const heights = await window.testTerrainTile(10, 500, 300, new AbortController().signal);
      map.setBearing(30);
      return {length: heights.length, first: heights[0], last: heights[255],
        pitch: map.getPitch(), bearing: map.getBearing(), rotation: !!map.options.rotateControl,
        track: controlElevation._layers.getLayers().some(layer => layer instanceof L.Polyline && map.hasLayer(layer)),
        rotateScript: performance.getEntriesByType('resource').some(entry => entry.name.includes('leaflet-rotate')),
        warning: document.querySelector('#map-warning').textContent};
    }""")
    assert result == {"length": 65536, "first": 100, "last": 356, "pitch": 45,
                      "bearing": 30, "rotation": True, "track": True,
                      "rotateScript": False, "warning": ""}, result


@then("mouse dragging does not rotate the 3D map")
def check_terrain_rotation_disabled(context):
    page = context.page
    if not page.evaluate("async () => !!(await navigator.gpu?.requestAdapter())"):
        context.scenario.skip("WebGPU is unavailable in this browser")
        return
    page.wait_for_selector("canvas.leaflet-3d", timeout=30000)
    bounds = page.locator("#map").bounding_box()
    x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down(button="right")
    page.mouse.move(x + 80, y, steps=4)
    page.mouse.up(button="right")
    assert page.evaluate("map.getBearing()") == 0


@then("the map falls back to 2D with a warning")
def check_terrain_fallback(context):
    page = context.page
    page.wait_for_function("document.querySelector('.maxele .summaryvalue').textContent === '200.00 m'", timeout=30000)
    assert "3D terrain unavailable" in page.locator("#map-warning").inner_text()
    assert page.locator("canvas.leaflet-3d").count() == 0
    assert page.evaluate("""() => map.options.rotateControl
      && performance.getEntriesByType('resource').some(entry => entry.name.includes('leaflet-rotate'))
      && !performance.getEntriesByType('resource').some(entry => entry.name.includes('leaflet-city-mapper'))""")


@then("the map reports the 3D terrain error")
def check_terrain_error(context):
    page = context.page
    if not page.evaluate("async () => !!(await navigator.gpu?.requestAdapter())"):
        context.scenario.skip("WebGPU is unavailable in this browser")
        return
    page.wait_for_function("document.querySelector('#map-warning').textContent.includes('Mapterhorn: HTTP 500')",
                           timeout=30000)


@then("the map reports the loading error")
def check_map_loading_error(context):
    context.page.wait_for_function(
        "document.querySelector('#map-warning').textContent.includes('Could not load the map:')",
        timeout=30000
    )
