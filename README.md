# QGIS TrackProfile2Web Plugin

Requires QGIS 4 with Qt WebEngine and a browser. The preview and exported pages load
Leaflet and leaflet-elevation 3.0.1 from a CDN, so they require internet access.
Map rotation and 3D terrain load additional libraries only when needed.
When exporting HTML and GeoJSON separately, serve both files over HTTP(S);
opening the HTML directly as a local file may block the GeoJSON request.

This plugin allows you to select a line layer and create an
interactive elevation profile:

![preview](img1.png)

For 2D line layers, the plugin automatically fetches elevations from
[Mapterhorn](https://mapterhorn.com/), so an internet connection is required.
It creates a temporary 3D copy and leaves the original layer unchanged.
Mapterhorn attribution is included in the generated map.

The workflow is very simple:

1. select a **line** layer loaded in QGIS and choose a base map in the settings sidebar
2. optionally change the appearance or profile settings
3. the preview updates automatically in QGIS. Navigate in the map and hover the mouse on the profile to
   see the position on the map

If you want you can export the map as a single `html` file or as `html` +
`geojson`, using QGIS's save dialogs. The settings panel is not included in
the exported page. The results can be easily embedded in a web page.

When 3D terrain is enabled, confirm opening the preview in the default browser
and keep QGIS open. Disabling 3D returns the preview to QGIS; the browser tab
can then be closed. The map rotation setting applies to both views.

The preview uses a temporary local server bound to `127.0.0.1` with a
session-specific address. It stops when the plugin is unloaded or QGIS closes.
Keep the preview address private while QGIS is running.

The settings interface, map configuration and styles are defined in
`track_profile_2_web.html`; `track_profile_2_web.py` handles QGIS integration and exports.
Chart and track settings include slope, units, distance markers, elevation colors,
map rotation, marker behavior, chart interaction, size, ticks and axis limits.
Limits use the selected units; chart size may be reduced to fit the available
space. Ascent and descent are calculated from the track's elevation samples.

Optional 3D terrain uses online Mapterhorn elevation tiles and requires WebGPU
in a secure context, a compatible browser/GPU and a base map allowing CORS.
If WebGPU is unavailable, the page displays a warning and uses the 2D map.
Tile loading errors are also displayed. Custom base maps must allow cross-origin
access; HTTPS pages cannot load HTTP tiles.

[Click to see a live example](https://www.faunalia.eu/it/dev/trackprofile2web).

Special thanks to [Raruto](https://github.com/Raruto) and his awesome [leaflet-elevation](https://github.com/Raruto/leaflet-elevation)
library!

## BDD tests

GitHub Actions runs the QGIS, browser, metadata and `@unit` scenarios on pushes
and pull requests.

Install `behave` in the QGIS 4 Python environment. From an OSGeo4W shell:

```shell
python-qgis -m behave test\features --tags=qgis
```

The browser scenarios require `behave`, `playwright`, Google Chrome and
internet access. Run them and the metadata scenario with:

```shell
python -m behave test\features --tags="not @qgis and not @unit"
```

Run packaging and upload scenarios without QGIS or browser dependencies:

```shell
python -m behave test\features --tags=@unit
```

## Releases

Configure the GitHub Actions secrets `QGIS_USERNAME` and `QGIS_PASSWORD` with
an OSGeo account permitted to upload the plugin. Push a new version tag
matching `metadata.txt` (for example `1.4` or `v1.4` for version `1.4`).

The CD workflow runs the CI tests, creates the plugin ZIP, and publishes it
to the QGIS plugin repository before creating a GitHub Release. If publishing
fails, rerun the failed jobs from GitHub Actions.
