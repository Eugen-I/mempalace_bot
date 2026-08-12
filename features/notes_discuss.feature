Feature: Notes found list — open and discuss
  As a user of the bot
  I want the notes agent to show found notes as buttons
  So that I can open a note and ask follow-up questions about it

  @notes @smoke @regression
  Scenario: Happy path — found note is opened and discussion is enabled
    Given the notes agent found notes ["Идеи [id=AAA]", "Покупки [id=BBB]"]
    When I click the "notes_view:0" button
    Then the note "Идеи" body is shown
    And discussion of note "AAA" is enabled

  @notes @negative
  Scenario: Notes list expired — user is asked to search again
    Given no notes list is cached
    When I click the "notes_view:0" button
    Then I see the "список заметок устарел" error

  @notes @negative
  Scenario: Index out of range — user is asked to search again
    Given the notes agent found notes ["Идеи [id=AAA]"]
    When I click the "notes_view:9" button
    Then I see the "список заметок устарел" error

  @notes @negative
  Scenario: Malformed index — invalid request
    Given the notes agent found notes ["Идеи [id=AAA]"]
    When I click the "notes_view:abc" button
    Then I see the "Неверный запрос" error

  @notes @edge
  Scenario: Note body read fails — graceful fallback, discussion still on
    Given the notes agent found notes ["Идеи [id=AAA]"]
    And reading note "AAA" fails
    When I click the "notes_view:0" button
    Then I see the "Текст недоступен" hint
    And discussion of note "AAA" is enabled

  @notes @edge
  Scenario: Follow-up question is routed with the opened note context
    Given discussion of note "AAA" is enabled
    When I send "что там про рассвет?"
    Then the agent question mentions "AAA" and "Идеи"
