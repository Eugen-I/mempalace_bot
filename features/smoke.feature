Feature: Project quality smoke checks
  As a maintainer
  I want baseline project quality checks
  So that the bot remains testable and maintainable

  @smoke @regression
  Scenario: Core project files exist
    Given the project root is available
    When I check the core files
    Then main.py should exist
    And README.md should exist
    And AGENTS.md should exist
