Feature: Plugin and QGIS requirements

  Scenario: Plugin metadata contains the required information
    Given the plugin metadata
    Then all mandatory metadata fields are present

  @qgis
  Scenario: Required QGIS providers are available
    Given QGIS is initialized
    Then the GDAL, OGR and PostgreSQL providers are available

  @qgis
  Scenario Outline: The dialog can be accepted or rejected
    Given a QGIS line layer with elevations
    When I <action> the dialog
    Then the dialog result is <result>

    Examples:
      | action | result   |
      | accept | accepted |
      | reject | rejected |

  @unit
  Scenario: Upload a plugin package
    Given a plugin package and a local repository
    When I upload the package with valid credentials
    Then the repository receives the package and returns its identifiers

  @unit
  Scenario: Reject invalid repository credentials
    Given a plugin package and a local repository
    When I upload the package with invalid credentials
    Then the upload fails without exposing credentials

  @unit
  Scenario: Report a rejected plugin package
    Given a plugin package and a local repository
    When the repository rejects the uploaded package
    Then the upload reports the rejection

  @unit
  Scenario: Report a missing plugin package
    When I upload a missing package with Make
    Then the upload command reports failure

  @unit
  Scenario: Reject insecure remote uploads
    When I configure an insecure remote upload URL
    Then the upload rejects the URL before requesting credentials

  @unit
  Scenario: Package translations in a plugin ZIP
    Given a plugin ready for packaging with two translations
    When I build the plugin package
    Then the ZIP contains the plugin and both compiled translations
    And the deployed plugin is unchanged

  @unit
  Scenario: Package a plugin without translations
    Given a plugin ready for packaging without translations
    When I build the plugin package without translations
    Then the ZIP contains only the plugin files
    And the deployed plugin is unchanged
