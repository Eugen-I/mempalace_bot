Feature: ChromaDB auto-update at bot startup (deps_guard)
  As the bot operator
  I want the bot to check for and install newer chromadb releases at startup
  So that the critical CVE-2026-45829 gets closed automatically when a fix
  is released, without manual intervention

  @deps @smoke @regression
  Scenario: Happy path — bot upgrades chromadb when a newer release exists
    Given chromadb 1.5.9 is installed and 1.6.0 is the latest on PyPI
    When the bot runs the chromadb auto-update check
    Then pip is asked to upgrade chromadb
    And the installed version is 1.6.0 after the upgrade
    And no CVE warning is logged

  @deps @negative
  Scenario: Network is unavailable — bot keeps current chromadb and warns
    Given PyPI is unreachable
    When the bot runs the chromadb auto-update check
    Then no pip upgrade is attempted
    And a CVE warning for version below 1.6.0 is logged

  @deps @negative
  Scenario: pip upgrade fails — bot keeps current version and warns
    Given chromadb 1.5.9 is installed, 1.6.0 is available and pip fails
    When the bot runs the chromadb auto-update check
    Then pip is asked to upgrade chromadb
    And the installed version is still 1.5.9
    And a CVE warning for version below 1.6.0 is logged

  @deps @negative
  Scenario: chromadb is not installed — nothing to update
    Given chromadb is not installed
    When the bot runs the chromadb auto-update check
    Then no pip upgrade is attempted
    And no error is raised

  @deps @edge
  Scenario: Version is already the latest — no action
    Given chromadb 1.6.0 is installed and 1.6.0 is the latest on PyPI
    When the bot runs the chromadb auto-update check
    Then no pip upgrade is attempted
    And no CVE warning is logged

  @deps @edge
  Scenario: Malformed PyPI response — graceful degradation
    Given PyPI returns malformed data
    When the bot runs the chromadb auto-update check
    Then no pip upgrade is attempted
    And no error is raised
