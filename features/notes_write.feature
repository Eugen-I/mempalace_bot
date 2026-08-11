Feature: Notes write operations (Apple Notes agent)
  As a user of the bot
  I want the notes agent to write to Apple Notes only after my confirmation
  So that no note is created, changed or deleted without my explicit consent

  @notes @smoke @regression
  Scenario: Happy path — note is created after confirmation
    Given the notes agent is ready for writes
    And the model script returns a tool call "notes_create" and then a final text
    When I run the notes agent and approve the confirmation
    Then the note is created with title "Тест"
    And the notes agent final answer contains the tool output

  @notes @negative
  Scenario: User cancels — nothing is created
    Given the notes agent is ready for writes
    And the model script returns a tool call "notes_create" and then a final text
    When I run the notes agent and cancel the confirmation
    Then no note is created
    And the model sees "Пользователь отклонил действие"

  @notes @negative
  Scenario: Delete requires double confirmation — one "Yes" is not enough
    Given the notes agent is ready for writes
    And the model script returns a tool call "notes_delete" and then a final text
    When I run the notes agent and approve the first confirmation only
    Then the note is not deleted
    And a second confirmation card is shown

  @notes @negative
  Scenario: No confirmation callback — write tools are unavailable
    Given the notes agent is ready for writes
    And the model script returns a tool call "notes_create" and then a final text
    When I run the engine without a confirmation callback
    Then the write tool is reported as unknown

  @notes @edge
  Scenario: Confirmation times out — action is cancelled
    Given the notes agent is ready for writes
    And the model script returns a tool call "notes_create" and then a final text
    When I run the notes agent and the confirmation times out
    Then no note is created

  @notes @edge
  Scenario: Read-only agent does not see write tools at all
    Given the notes agent is ready for writes
    And the model script returns a tool call "notes_create" and then a final text
    When I run the notes agent with writes disabled
    Then the write tool is reported as unknown
