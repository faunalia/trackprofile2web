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
  Scenario: Reject a line without elevations
    Given a QGIS line layer without elevations
    When I update the preview
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
