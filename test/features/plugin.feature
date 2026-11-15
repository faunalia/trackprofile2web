Feature: Plugin and QGIS requirements

  Scenario: Plugin metadata contains the required information
    Given the plugin metadata
    Then all mandatory metadata fields are present

  @qgis
  Scenario: Required QGIS providers are available
    Given QGIS is initialized
    Then the GDAL, OGR and PostgreSQL providers are available

  @qgis
  Scenario: Recognize the WGS 84 reference system
    Given QGIS is initialized
    When I load the WGS 84 WKT and sample raster
    Then both reference systems describe WGS 84

  @qgis
  Scenario Outline: The dialog can be accepted or rejected
    Given a QGIS line layer with elevations
    When I <action> the dialog
    Then the dialog result is <result>

    Examples:
      | action | result   |
      | accept | accepted |
      | reject | rejected |

  @qgis
  Scenario: Load an Afrikaans translation
    Given QGIS is initialized
    When I compile and install the Afrikaans translation
    Then "Good morning" is translated as "Goeie more"
