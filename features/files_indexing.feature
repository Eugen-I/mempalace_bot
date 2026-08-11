Feature: Раздельная индексация файлов Apple Notes
  As a user of the bot
  I want files (exported notes, txt/md documents) to be indexed separately from
  note texts and searchable full-text
  So that file content is discoverable and can feed the Knowledge Graph

  @files @smoke @regression
  Scenario: Happy path — новый файл индексируется и находится поиском
    Given в директории заметок есть файл "идеи.txt" с текстом "план на лето"
    When я запускаю индексацию директории
    Then статус файла "идеи.txt" — "indexed"
    And полнотекстовый поиск по "план" возвращает "идеи.txt"
    And статистика индекса: total_files = 1

  @files @negative
  Scenario: Повторная индексация того же контента не создаёт дубликат
    Given файл "заметка.txt" уже проиндексирован
    When я индексирую директорию ещё раз
    Then статистика индекса: total_files = 1
    And статус повторной обработки — "added: false"

  @files @negative
  Scenario: Директория не существует — ошибка
    When я запускаю индексацию несуществующей директории
    Then я получаю FileNotFoundError
    And никакие файлы не добавлены

  @files @negative
  Scenario: Недоступная модель эмбеддингов — graceful degradation
    Given модель Ollama недоступна
    When я вызываю build_embeddings
    Then функция возвращает False
    And семантический поиск возвращает полнотекстовые результаты

  @files @edge
  Scenario: Пустой текст файла
    Given в директории есть пустой файл "пусто.txt"
    When я запускаю индексацию директории
    Then файл проиндексирован с 0 чанками
    And поиск по "что-то" не находит его

  @files @edge
  Scenario: Файл ровно в размер чанка
    Given файл содержит ровно 800 символов
    When я запускаю индексацию
    Then файл разбит ровно на 1 чанк
