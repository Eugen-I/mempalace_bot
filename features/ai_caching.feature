Feature: AI response caching
  As a user
  I want repeated questions to get instant answers
  So that I save time and API quota

  @smoke @regression
  Scenario: Happy path — same query returns cached response
    Given I asked "What is mempalace?" and got a response
    When I ask "What is mempalace?" again
    Then I should get the cached response instantly

  @negative
  Scenario: Different question does not match cache
    Given I asked "What is mempalace?" and got a response
    When I ask "Tell me about python"
    Then I should get a fresh response from AI

  @negative
  Scenario: Cache miss on empty query
    Given I asked "" and nothing was cached
    When I ask ""
    Then I should get no cached response

  @negative
  Scenario: Expired cache returns fresh response
    Given I asked "What is AI?" and it was cached 10 minutes ago
    When the cache TTL has passed
    Then asking "What is AI?" should hit the AI, not cache

  @edge
  Scenario: Very similar but not identical query
    Given I asked "What is artificial intelligence?" and got a response
    When I ask "What is AI?"
    Then I should get the cached response if similarity exceeds threshold

  @edge
  Scenario: Cache respects max size
    Given the cache is full with 200 entries
    When I ask a new question
    Then the oldest entry should be evicted
