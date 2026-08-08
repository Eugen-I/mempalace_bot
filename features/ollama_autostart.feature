Feature: Ollama autostart and AI availability
  As a user
  I want the bot to start the local Ollama server automatically
  So that the AI works even after the machine reboot

  @smoke @regression
  Scenario: Happy path — Ollama started on demand
    Given the current AI model is an Ollama model (e.g. "qwen2.5:7b")
    And Ollama server is not running
    When I send a message that requires AI
    Then the bot should start `ollama serve` in the background
    And I should get an AI answer from the Ollama model

  @negative
  Scenario: Ollama cannot start — friendly error
    Given the current AI model is an Ollama model
    And `ollama` CLI is not installed
    When I send a message that requires AI
    Then I should get a message "Не удалось подключиться к Ollama"
    And the raw technical traceback should only go to the bot log

  @negative
  Scenario: Connection refused at request time — friendly error
    Given the Ollama server stopped between check and request
    When I send a message that requires AI
    Then I should get a message "Не удалось подключиться к Ollama"
    And no raw "Connection refused" text should reach the user

  @negative
  Scenario: Gemini/OpenAI model — no Ollama side effects
    Given the current AI model is "gemini-flash-latest"
    When I send a message that requires AI
    Then the bot should not start or check the Ollama server

  @edge
  Scenario: Prewarm at bot startup
    Given the current AI model is an Ollama model
    When the bot starts
    Then the bot should pre-warm Ollama in a background thread
    And the bot must start polling even if Ollama pre-warm fails

  @edge
  Scenario: First call latency after reboot
    Given the Ollama server is starting after a reboot
    When I send a message that requires AI within the first 30 seconds
    Then the bot should wait for the server to become ready
    And then answer with the Ollama model
