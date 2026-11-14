# Garmin local-first integration
# Every scenario uses a temporary SQLite database, a temporary raw archive,
# fake FIT decoding and no network access.  The online Garmin mode (P8) is
# intentionally out of scope here; it is tested separately when enabled.

@garmin @regression
Feature: Garmin local health reports and adaptive training plan
  As a user
  I want my Garmin exports to become a health report and a safe training plan
  So that I can act on my own data without giving it to a cloud service

  Background:
    Given a clean local Garmin store

  @smoke
  Scenario: Wellness export becomes a health PDF with charts
    Given a wellness export with one day of data
    When I import the wellness export and build the health PDF
    Then the import succeeds with one day
    And the database contains one daily row
    And the health PDF contains charts and key metrics

  Scenario: Re-importing the same wellness export is idempotent
    Given a wellness export with one day of data
    When I import the wellness export twice
    Then the second import is skipped
    And the database contains one daily row

  Scenario: Corrupt wellness ZIP fails without changing the database
    Given a corrupt wellness ZIP
    When I import the wellness export
    Then the import fails without daily rows
    And the raw export is preserved

  Scenario: Full export without known activity files is reported as unsupported
    Given a full export ZIP without activity files
    When I import the full export
    Then the full export reports no activity files
    And the raw export is preserved

  Scenario: Missing metrics are marked with a dash and listed
    Given only sleep data for fourteen days
    When I build the health PDF
    Then the report lists missing inputs
    And the health PDF marks missing values with a dash

  Scenario: PDF contains AI causes and whitelisted citations
    Given fourteen days of complete Garmin data
    When I generate AI narration with a valid fake model
    And I build the health PDF with the narration
    Then the health PDF contains the AI cause and citations

  Scenario: Incomplete profile produces clarifying questions
    Given an incomplete profile and insufficient data
    When I ask for plan clarification
    Then the bot asks between one and three questions

  Scenario: Medications produce a conservative plan and a doctor sheet
    Given a profile with serotonergic medications
    When I build the plan and both plan PDFs
    Then the plan is conservative
    And the doctor sheet contains medication details
    And the plan PDF excludes medication doses

  Scenario: Chest pain blocks the plan and escalates
    Given a user reports chest pain during exercise
    When I assess the safety of the request
    Then the red flag blocks the plan
    And the escalation points to urgent help

  Scenario: Poor sleep yields amber readiness and a deload review
    Given seven days of poor sleep
    When I assess readiness and run the weekly review
    Then readiness is amber
    And the weekly review recommends a deload

  Scenario: AI failure falls back to deterministic text
    Given fourteen days of complete Garmin data
    When I generate AI narration with a broken model
    Then the narration is deterministic
    And the health PDF labels the deterministic analysis

  Scenario: Retention extension and cleanup
    Given an old and a recent Garmin day
    When I check retention, extend it and run cleanup
    Then retention is due before the extension
    And the extension postpones retention
    And cleanup removes the old day and keeps the recent day
