Feature: Event-driven background processing
  As a developer
  I want side effects (sync, fact extraction) to happen in the background
  So that the user gets AI response without waiting for secondary tasks

  @smoke @regression
  Scenario: Happy path — events trigger handlers
    Given I have handlers for AI_RESPONSE_SENT
    When AI response is sent to user
    Then the sync handler should run in background

  @negative
  Scenario: Handler failure does not block others
    Given one handler throws an exception
    When the event is published
    Then other handlers should still execute normally

  @negative
  Scenario: No handlers for event — no error
    Given no handlers are subscribed to CHAT_CREATED
    When that event fires
    Then nothing should happen

  @negative
  Scenario: Double subscribe runs handler twice
    Given the same handler is subscribed twice
    When the event fires
    Then the handler should be called twice

  @edge
  Scenario: Unsubscribed handler does not run
    Given a handler was subscribed and then unsubscribed
    When the event fires
    Then the handler should not be called

  @edge
  Scenario: Background publish does not block caller
    Given a slow handler that takes 5 seconds
    When I publish in background
    Then I should continue immediately without waiting
