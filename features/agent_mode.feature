Feature: Agent Mode (qwen2.5 with tools)
  As a user of the bot
  I want an agent mode that can use tools in a loop
  So that I get answers grounded in my mempalace data

  @agent @smoke @regression
  Scenario: Happy path — agent answers using a tool
    Given the agent is enabled in my settings
    And a tool "mp_kg_stats" is registered that returns "Комнат в дворце: 7"
    And the model script returns a tool call "mp_kg_stats" and then a final text
    When I run the agent with the user prompt "сколько у меня комнат"
    Then I see the step status "🔧 Шаг 1/5: mp_kg_stats…"
    And the tool "mp_kg_stats" is executed with valid arguments
    And the final answer contains the tool output
    And the agent finished in 2 iterations without error

  @agent @negative
  Scenario: Agent disabled — routing sends the message to ordinary AI
    Given the agent is disabled in my settings
    When I ask the routing gate about the message "обычный вопрос"
    Then the routing gate returns False
    And the agent is not started

  @agent @negative
  Scenario: Command bypasses the agent
    Given the agent is enabled in my settings
    When I ask the routing gate about the message "/unknowncmd something"
    Then the routing gate returns False
    And the agent is not started

  @agent @negative
  Scenario: Model never calls a tool — fallback answer
    Given the agent is enabled in my settings
    And the model script returns only a plain text without tool calls
    When I run the agent with the user prompt "привет"
    Then the final answer equals the model text
    And the agent finished with reason "answer" without error

  @agent @negative
  Scenario: Unknown tool name — agent continues and reports it
    Given the agent is enabled in my settings
    And the model script calls the unknown tool "no_such_tool"
    When I run the agent with the user prompt "что-нибудь"
    Then the final answer contains the text "не существует"
    And the agent finished without crash

  @agent @edge
  Scenario: Tool failure — error is visible and loop continues
    Given the agent is enabled in my settings
    And a tool "mp_boom" is registered that raises an exception
    And the model script calls "mp_boom" and then returns a final text
    When I run the agent with the user prompt "найди факты"
    Then I see the step status "🔧 Шаг 1/5: mp_boom…"
    And the final answer contains the text "Ошибка"
    And the agent finished in 2 iterations without crash

  @agent @edge
  Scenario: Iteration limit reached
    Given the agent is enabled in my settings
    And a tool "mp_kg_stats" is registered that returns "Комнат в дворце: 7"
    And the model script requests a tool on every iteration
    When I run the agent with the user prompt "продолжай работать"
    Then I see the step status "🔧 Шаг 5/5: mp_kg_stats…"
    And the result error contains the word "лимит"

  @agent @smoke @regression
  Scenario: Happy path — agent answers from the palace via mp_search
    Given the agent is enabled in my settings
    And the MCP server returns "Ящик 1: размышления о шопенгауэре"
    And the model script calls "mp_search" with the query "шопенгауэре" and then returns "найдено: шопенгауэре"
    When I run the agent with the user prompt "что я думал о шопенгауэре"
    Then I see the step status "🔧 Шаг 1/5: mp_search…"
    And the MCP tool "mempalace_search" was called with the query "шопенгауэре"
    And the final answer contains the text "шопенгауэре"

  @agent @smoke
  Scenario: Happy path — agent searches and reads an Apple Note
    Given the agent is enabled in my settings
    And the Apple Notes index contains the note "Философия воли" with id "note1"
    And the model script calls "notes_search" and then "notes_read" and then returns "идея из заметки: воля"
    When I run the agent with the user prompt "что в заметке про волю"
    Then I see the step status "🔧 Шаг 1/5: notes_search…"
    And the tool "notes_read" was called with the id "note1"
    And the final answer contains the text "воля"

  @agent @smoke
  Scenario: Agent finds a note by a word from its text and cites it
    Given the agent is enabled in my settings
    And a note "Философия воли" with id "note1" and text "Размышления о воле и представлении" is in the Apple Notes index
    And the model script calls "notes_search" and then "notes_read" and then returns "Цитата из заметки «Философия воли»: «Размышления о воле»"
    When I run the agent with the user prompt "что в заметках про волю"
    Then I see the step status "🔧 Шаг 1/5: notes_search…"
    And the tool "notes_read" was called with the id "note1"
    And the final answer contains the text "Философия воли"

  @agent @smoke @semantic
  Scenario: Semantic search finds a note by meaning even if the query word is absent from the title
    Given the agent is enabled in my settings
    And semantic search returns the note "Идеи по отпуску" with id "note7" for the query "хочу отдохнуть"
    And the model script calls "notes_search" with the query "хочу отдохнуть" and then "notes_read" with id "note7" and then returns "Цитата из заметки «Идеи по отпуску»: «поехать на море»"
    When I run the agent with the user prompt "что я писал про отдых"
    Then I see the step status "🔧 Шаг 1/5: notes_search…"
    And the tool "notes_read" was called with the id "note7"
    And the final answer contains the text "поехать на море"

  @agent @negative @semantic
  Scenario: Semantic search unavailable — agent answers without crash
    Given the agent is enabled in my settings
    And the semantic search is unavailable
    And the model script returns only a plain text without tool calls
    When I run the agent with the user prompt "что я писал про отпуск"
    Then the final answer equals the model text
    And the agent finished without crash
