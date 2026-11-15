Feature: Create an elevation profile

  @qgis
  Scenario: Preview a line with elevations
    Given a QGIS line layer with elevations
    When I update the preview
    Then the preview contains the line coordinates and elevations
    And the export buttons are enabled
    And the QGIS preview displays the elevation chart

  @qgis
  Scenario: Load and unload the plugin in QGIS
    Given a QGIS line layer with elevations
    When the plugin is loaded and unloaded
    Then its menu and toolbar actions are registered and removed

  @qgis
  Scenario: Open and reopen the dialog maximized
    Given a QGIS line layer with elevations
    Then the plugin opens the dialog maximized each time

  @qgis
  Scenario: Add elevations to a line from Mapterhorn
    Given a QGIS line layer without elevations
    When Mapterhorn elevation tiles are available
    And I update the preview
    And I export the HTML and GeoJSON
    Then the preview contains the Mapterhorn elevations
    And the original layer remains 2D
    And the exported GeoJSON contains the Mapterhorn elevations

  @qgis
  Scenario: Automatically refresh the preview
    Given a QGIS line layer without elevations
    When Mapterhorn elevation tiles are available
    Then the preview follows option and layer changes without refetching unchanged elevations

  @qgis
  Scenario: Use the HTML settings panel
    Given a QGIS line layer with elevations
    Then the HTML controls change the preview and export a clean page

  @qgis
  Scenario: Keep exports disabled when Mapterhorn has no data
    Given a QGIS line layer without elevations
    When Mapterhorn elevation tiles are unavailable
    And I update the preview
    Then the export buttons remain disabled

  @qgis
  Scenario: Export a profile with a separate GeoJSON file
    Given a QGIS line layer with elevations
    When I update the preview
    And I export the HTML and GeoJSON
    Then the HTML references the exported GeoJSON
    And the preview still contains embedded data

  @qgis
  Scenario: Export the preview as a single HTML file
    Given a QGIS line layer with elevations
    When I update the preview
    And I export the single HTML file
    Then the exported HTML contains the embedded track

  @qgis
  Scenario: Preserve multipart geometry when reprojecting
    Given a projected multipart QGIS line layer with elevations
    When I update the preview
    And I export the HTML and GeoJSON
    Then both outputs contain separate reprojected line parts

  @web
  Scenario: Render an embedded elevation profile
    Given an embedded elevation profile in the HTML template
    When I open the profile in a browser
    Then the chart and its elevation summary are displayed

  @web
  Scenario: Render a profile from a separate GeoJSON file
    Given an elevation profile in a separate GeoJSON file
    When I open the profile in a browser
    Then the chart and its elevation summary are displayed

  @web
  Scenario: Render an attached profile
    Given an attached elevation profile in the HTML template
    When I open the profile in a browser
    Then the chart and its elevation summary are displayed
    And the profile is attached to the map

  @web
  Scenario: Render customized chart and track options
    Given an elevation profile with customized chart and track options
    When I open the profile in a browser
    Then the customized options and imperial summary are displayed

  @web
  Scenario: Render the track on 3D terrain
    Given an elevation profile with 3D terrain
    When I open the profile in a browser
    Then the map displays 3D terrain and the elevation profile

  @web
  Scenario: Fall back when 3D is unavailable
    Given an elevation profile with 3D terrain but no WebGPU
    When I open the profile in a browser
    Then the map falls back to 2D with a warning

  @web
  Scenario: Report unavailable 3D elevation tiles
    Given an elevation profile with 3D terrain and unavailable elevation tiles
    When I open the profile in a browser
    Then the map reports the 3D terrain error
