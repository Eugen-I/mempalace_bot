Feature: Notes found list — open, discuss, storm and save a note
  As a user of the bot
  I want the notes agent to show found notes as buttons with actions
  So that I can open a note, discuss it with the agent, run a surreal
  brainstorm on its text, or save it into MemPalace

  @notes @smoke @regression
  Scenario: Happy path — found note is opened with action buttons and discussion is enabled
    Given the notes agent found notes ["Идеи [id=AAA]", "Покупки [id=BBB]"]
    When I click the "notes_view:0" button
    Then the note "Идеи" body is shown
    And the action buttons include "notes_discuss:0"
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
  Scenario: Follow-up questions keep the opened note context
    Given discussion of note "AAA" is enabled
    When I send "что там про рассвет?"
    Then the agent question mentions "AAA" and "Идеи"
    And discussion of note "AAA" is still enabled

  @notes @smoke @regression
  Scenario: Discuss button enables discussion with folder hint
    Given the notes agent found notes ["Идеи [id=AAA] (папка: Notes)"]
    When I click the "notes_discuss:0" button
    Then discussion of note "AAA" is enabled
    And I see the "Notes" hint

  @notes @negative
  Scenario: Storm on empty note body — no brainstorming possible
    Given the notes agent found notes ["Пустая [id=AAA]"]
    And note "AAA" body is empty
    When I click the "notes_storm:0" button
    Then I see the "Текст заметки недоступен" error

  @notes @negative
  Scenario: Save on empty note body — nothing to save
    Given the notes agent found notes ["Пустая [id=BBB]"]
    And note "BBB" body is empty
    When I click the "notes_save:0" button
    Then I see the "Текст заметки недоступен" error

  @notes @negative
  Scenario: Action on stale list — user is asked to search again
    Given no notes list is cached
    When I click the "notes_storm:0" button
    Then I see the "список заметок устарел" error

  @notes @edge
  Scenario: Storm uses the note text as context
    Given the notes agent found notes ["Фудзи [id=CCC]"]
    And note "CCC" body is "вид на гору в тумане"
    When I click the "notes_storm:0" button and the model answers
    Then the storm prompt contains "вид на гору в тумане"

  @notes @edge
  Scenario: Stop button ends the discussion
    Given discussion of note "AAA" is enabled
    When I click the "notes_stop:0" button
    Then I see the "Обсуждение завершено" hint
    And discussion of note "AAA" is disabled

  @notes @smoke @regression
  Scenario: Long note is shown as ONE message with paging arrows and back button
    Given the notes agent found notes ["Большая [id=DDD]"]
    And note "DDD" body is long
    When I click the "notes_view:0" button
    Then I see the "Страница 1/2" hint
    And the action buttons include "notes_page:0:1"
    And the action buttons include "notes_back:0"
    And I do not see several messages

  @notes @smoke
  Scenario: Next page arrow flips to the second page
    Given the notes agent found notes ["Большая [id=DDD]"]
    And note "DDD" body is long
    And the note "DDD" is open on the first page
    When I click the "notes_page:0:1" button
    Then I see the "Страница 2/2" hint

  @notes @negative
  Scenario: Paging with an expired note session is refused
    Given no notes list is cached
    When I click the "notes_page:0:1" button
    Then I see the "Сессия заметки истекла" error

  @notes @smoke @regression
  Scenario: Back to list restores the found notes list
    Given the notes agent found notes ["Идеи [id=AAA]", "Покупки [id=BBB]"]
    When I click the "notes_view:0" button
    And I click the "notes_back:0" button
    Then the notes list is shown again with "notes_view:0" and "notes_view:1"
