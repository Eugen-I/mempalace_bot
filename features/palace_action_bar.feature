Feature: Action Bar in the Palace
  As a user of the Palace section
  I want a unified action bar under every Palace answer
  So that I can analyze, web-search, save, scroll and navigate back in one place

  @smoke @regression
  Scenario: Happy path — long record is readable via pagination and back works
    Given I open a record in the Palace room "dreams/first"
    And the record text is 3000 characters long
    When the record is rendered with the action bar
    Then I see one message with the action bar buttons [🤖 Анализ ИИ] [🌐 Поиск в интернете] [💾 Сохранить]
    And I see pagination indicator [📄 1/2] with the next button [▶️ Вперёд]
    And I see the button [🔙 Вернуться к списку]
    When I press [▶️ Вперёд]
    Then the same message shows page 2 with indicator [📄 2/2]
    When I press [🔙 Вернуться к списку]
    Then I see the record list of the room "dreams/first"

  @negative
  Scenario: No parent screen — back button is hidden
    Given a Palace answer without a parent screen context
    When the action bar is rendered
    Then there is no [🔙 Вернуться к списку] button

  @negative
  Scenario: Expired session — actions show an alert
    Given I press a pagination button of an answer older than 30 minutes
    When the handler receives the callback
    Then I get an alert "Сессия истекла. Откройте заново."
    And the message is not modified

  @negative
  Scenario: AI failure during analysis
    Given I press [🤖 Анализ ИИ] and choose "Анализ ответа"
    When the AI call raises an exception
    Then I see an error message with the word "Ошибка"
    And the bot does not crash

  @negative
  Scenario: Empty web search query
    Given I press [🌐 Поиск в интернете]
    When the AI returns an empty or whitespace-only query
    Then I see an error message with the word "Ошибка"

  @edge
  Scenario: Text exactly 1500 characters
    Given the answer text is exactly 1500 characters
    When the action bar is rendered
    Then pagination buttons are not shown
    And indicator [📄 1/1] is not shown

  @edge
  Scenario: Text longer than 3000 characters
    Given the answer text is 4500 characters
    When the action bar is rendered
    Then I see pagination indicator [📄 1/3] with the next button [▶️ Вперёд]
    And pressing [▶️ Вперёд] twice shows [📄 3/3] without a next button
