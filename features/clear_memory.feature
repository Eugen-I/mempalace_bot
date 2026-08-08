Feature: Полная очистка базы MemPalace (clear_memory.command)
  As a user
  I want to fully or selectively wipe MemPalace data (database, wings, rooms, user folders, temp files)
  So that I can start filling the palace from scratch or free disk space

  @smoke @regression
  Scenario: Happy path — полная очистка всего
    Given MemPalace contains wings, user folders, database and temp files
    And the bot is not running
    When I choose "Полная очистка" and decline backup
    And I confirm the wipe twice
    Then all wings, user folders, database (~/.mempalace) and temp files are deleted
    And only the empty MemPalace folder remains

  @negative
  Scenario: Отмена на первом подтверждении
    Given I choose "Полная очистка"
    When I answer "n" to the first confirmation
    Then nothing is deleted
    And the warning message is shown

  @negative
  Scenario: Отмена при выборочной очистке
    Given I choose a wing, room or user folder
    When I answer "n" to the delete confirmation
    Then the selected items remain untouched

  @negative
  Scenario: Отказ от бэкапа не блокирует очистку
    Given I choose "Полная очистка"
    When I answer "n" to the backup question
    Then no backup archive is created
    And the wipe proceeds normally

  @negative
  Scenario: Бот запущен — предупреждение
    Given the bot process (main.py) is running
    When I choose "Полная очистка"
    Then the script warns about the running bot
    And asks whether to continue anyway

  @edge
  Scenario: Список пуст — ничего удалять
    Given there are no wings, user folders or database items
    When I choose any cleanup option
    Then the script reports that nothing was found and returns to the menu

  @edge
  Scenario: Неверный ввод в меню
    Given the main menu is shown
    When I enter a non-numeric or out-of-range choice
    Then the script shows "Неверный выбор" and returns to the menu

  @edge
  Scenario: Удаление крыла без комнат
    Given a wing has no rooms
    When I select it for cleanup
    Then the script offers to delete the whole wing

  @edge
  Scenario: Бэкап создаётся с совместимым именем
    Given I choose "Создать бэкап"
    When the backup is created
    Then the archive is named mempalace_backup_*.tar.gz in ~/Documents
    And it excludes venv, __pycache__ and .git
