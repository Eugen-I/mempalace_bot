Feature: Session persistence across restarts
  As a user
  I want my in-progress operations to survive bot restarts
  So that I don't lose work if the bot goes down

  @smoke @regression
  Scenario: Happy path — state survives restart
    Given I was in the middle of creating a tunnel
    When the bot restarts
    Then I should be able to continue from where I left off

  @negative
  Scenario: Expired state is cleaned up
    Given I started an operation 35 minutes ago
    When the bot checks for expired states
    Then my old state should be removed

  @negative
  Scenario: Missing key returns default
    Given no state was saved for my session
    When I ask for my state
    Then I should get a default value, not an error

  @negative
  Scenario: Malformed data in store
    Given the store has corrupted data for my key
    When I retrieve it
    Then I should get the default value without crashing

  @edge
  Scenario: TTL prevents stale state
    Given I started a YouTube download 10 minutes ago with TTL 5 min
    When I try to continue
    Then my state should be gone

  @edge
  Scenario: Namespace isolation
    Given I have a tunnel state in namespace "tunnels"
    When I query namespace "youtube"
    Then I should not see tunnel data
