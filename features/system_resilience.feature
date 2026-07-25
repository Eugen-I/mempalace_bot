Feature: System graceful degradation
  As a user
  I want the bot to keep working when components fail
  So that I never get stuck waiting

  @smoke @regression
  Scenario: Happy path — all systems healthy
    Given Palace, Memory and AI are all available
    When I send a message
    Then I should get a full-featured response with Palace context

  @negative
  Scenario: Palace down — bot still answers
    Given Palace search is failing
    When I send a message
    Then I should get a response without Palace context

  @negative
  Scenario: Memory store down — bot still answers
    Given Memory store is failing
    When I send a message
    Then I should get a response without my past facts

  @negative
  Scenario: AI API down — emergency mode
    Given AI API is returning errors
    When I send a message
    Then I should get an emergency fallback message

  @edge
  Scenario: Recovery from Palace failure
    Given Palace was down and bot degraded to MEDIUM
    When Palace becomes available again
    Then bot should return to FULL mode automatically

  @edge
  Scenario: Component repeatedly fails — circuit opens
    Given Palace fails 3 times in a row
    When I send another request
    Then the circuit should open and skip Palace calls immediately
