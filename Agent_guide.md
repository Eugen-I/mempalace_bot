AGENT_GUIDE.md - Руководство для ИИ-агента по развитию mempalace_bot

Версия: 1.0
Дата: 2026-08-08
Проект: https://github.com/Eugen-I/mempalace_bot
Назначение: Пошаговое руководство для AI-агента (Cursor/Copilot/AutoGPT) по улучшению кодовой базы

---

> ## ⚠️ СТАТУС ВЫПОЛНЕНИЯ (обновлено 2026-08-13)
> **ВСЕ 5 ЗАДАНИЙ ЭТОГО РУКОВОДСТВА УЖЕ ВЫПОЛНЕНЫ. ПОВТОРНО НЕ РЕАЛИЗОВЫВАТЬ.**
>
> | Задание | Статус | Где / когда |
> |---------|--------|-------------|
> | 1. Backup-файлы + .gitignore | ✅ выполнено | Правила в `.gitignore:60-68`, backup-файлов в репо нет (проверено 2026-08-13) |
> | 2. aiofiles в async-функциях | ✅ выполнено | Коммит `37056e8`; `services/memory.py` — `aiofiles.open` в `_load_memories_async`/`_save_memories_async`. `services/kv_store.py` aiofiles НЕ нужен — он работает через sqlite3 (синхронно, без async-функций) |
> | 3. Надёжный парсинг JSON от LLM | ✅ выполнено | `services/json_parser.py` (extract_json_from_text/safe_parse_llm_json) + `tests/test_json_parser.py`; подключён в `kg_enricher.py:188`, `memory.py:160`, `brainstorm.py:22` |
> | 4. selectolax вместо regex | ✅ выполнено | Коммит `37056e8`; `services/web_search.py:76-79` (HTMLParser), `selectolax>=0.3.11` в requirements.txt:19; покрыто `tests/test_web_search.py` (42 теста) |
> | 5. Векторный поиск | ✅ выполнено | Коммит `72db447` (2026-08-13). **Реализован НЕ как в гайде** (ChromaDB+ST отклонён пользователем — 500MB, дублирование): гибрид keyword+семантика на существующем `services/notes_embeddings.py` (bge-m3 через Ollama). См. ниже. |
>
> **Как выполнено Задание 5 (если потребуется поддержка):**
> - NEW `services/memory_embeddings.py`: SQLite `DATA_DIR/memory_embeddings.sqlite`, таблица `memory_embeddings(user_id, fact, vector, model, PRIMARY KEY(user_id, fact))`; `build_index(user_id, force)` (батчи 40, авто-rebuild по count-сверке `_index_matches`), `search_similar(query, user_id, limit)` — косинусная близость, `limit<1 → EmbeddingsError`, пустой запрос → `[]`, graceful degradation (модель недоступна / embed fail / битый BLOB → `[]`). Переиспользует `_call_embed`/`_cosine`/`is_model_available`/`EMBED_MODEL`/`EMBED_DIM`/`EmbeddingsError` из `notes_embeddings.py` (НЕ дублировать код).
> - `services/memory.py::retrieve_facts` → гибрид: keyword-результаты (порядок сохранён) + семантическое дополнение через `_extend_with_semantic` (дедуп по тексту, лимит max_results, любое исключение → только keyword).
> - Тесты: `tests/test_memory_embeddings.py` (25 unit, покрытие 100%), `tests/test_memory.py` (8 гибридных + autouse-мок `search_similar` для детерминизма), BDD `features/memory_hybrid.feature` 6/6. Итог на момент закрытия: **3377 passed**, flake8 0, mypy 0, bandit 73 (базлайн), behave 21 features passed.
> - **Осталось из итогового чек-листа гайда**: ручная проверка бота (запуск + основные функции) — на усмотрение пользователя; `.git-hooks/check_no_secrets.py` — уже прогоняется, 0 секретов.
>
> Актуальное состояние проекта и точка возобновления — в `TESTING_PROGRESS.md` (читать ПЕРЕД любой сессией).

---

ПРАВИЛА РАБОТЫ АГЕНТА

ЖЕЛЕЗНОЕ ПРАВИЛО 1: Проверка актуальности кода

Перед началом ЛЮБОЙ задачи агент ОБЯЗАН:

1. Проверить локальную версию: Выполнить git status и git log --oneline -20
2. Сравнить с GitHub: Выполнить git fetch origin && git log HEAD..origin/main --oneline
3. Выявить расхождения: Если есть коммиты на GitHub, которых нет локально (или наоборот):
   - СТОП. Не выполнять задачу.
   - Сообщить пользователю: "Обнаружены расхождения между локальной и GitHub версией. Локальная версия содержит X новых коммитов, которых нет на GitHub. Пожалуйста, обновите репозиторий (git push) или уточните, работать ли с локальной версией?"
4. Дождаться подтверждения от пользователя перед продолжением.

ЖЕЛЕЗНОЕ ПРАВИЛО 2: Проверка существующих решений

Перед реализацией ЛЮБОЙ новой функции агент ОБЯЗАН:

1. Поиск по коду: Использовать grep -r "ключевые_слова" . --include="*.py"
2. Поиск по Git: Использовать git log --all --oneline --grep="ключевые_слова"
3. Проверить TODO/FIXME: grep -rn "TODO\|FIXME" .
4. Если функция уже реализована:
   - Сообщить пользователю: "Функция X уже присутствует в коде (файл Y, строка Z). Показать текущую реализацию?"
   - Не дублировать код.

ЖЕЛЕЗНОЕ ПРАВИЛО 3: Протокол коммуникации

Агент ОБЯЗАН предлагать пользователю варианты выбора перед каждым критическим действием.

Пример формата запроса:

Задача: Внедрить векторный поиск для замены keyword-поиска

Текущее состояние:
- Файл: services/memory.py
- Метод: _score_fact_by_keyword_matches()
- Проблема: Не учитывает синонимы и перефразирования

Варианты реализации:
[1] Sentence-Transformers + ChromaDB (рекомендуется)
    Плюсы: Быстрый, локальный, хорошо интегрируется
    Минусы: Требует 500MB на модель
[2] OpenAI Embeddings + Qdrant
    Плюсы: Высокое качество, не требует GPU
    Минусы: Платный API, зависимость от сети
[3] Ollama Embeddings (локально)
    Плюсы: Бесплатно, приватно
    Минусы: Медленно, требует ресурсов

Какой вариант выбираем? Или предложить другой?

---

ПОШАГОВЫЕ ЗАДАНИЯ

ЗАДАНИЕ 1: Очистка backup-файлов и настройка .gitignore

Приоритет: Критический
Время: 10 минут

Шаги выполнения:

1. Проверить наличие backup-файлов:
   Команда: find . -name "*.backup*" -o -name "*.bak*" | grep -v ".git/"

2. Если файлы найдены:
   - Создать временную папку ~/backup_before_cleanup_DATE
   - Скопировать туда все backup-файлы
   - Показать пользователю список файлов для удаления
   - Получить подтверждение перед удалением

3. Обновить .gitignore:
   Добавить строки:
   *.backup
   *.backup[0-9]*
   *.bak
   *.bak[0-9]*
   *.old
   *.orig
   *~
   .vscode/
   .idea/

4. Удалить из Git истории:
   Команда: git rm --cached handlers/palace/navigation.py.backup*
   Команда: git commit -m "chore: remove backup files from repository"

Критерии успеха:
- Команда find . -name "*.backup*" -o -name "*.bak*" возвращает пустой результат
- .gitignore содержит правила для backup-файлов
- git status показывает чистое рабочее дерево
- Backup-файлы сохранены в безопасном месте вне репозитория

Тесты:

Тест 1: Проверка отсутствия backup-файлов
Команда: if find . -name "*.backup*" -o -name "*.bak*" | grep -q .; then echo "FAIL: Найдены backup-файлы"; exit 1; else echo "PASS: Backup-файлы отсутствуют"; fi

Тест 2: Проверка .gitignore
Команда: if grep -q "\.backup" .gitignore && grep -q "\.bak" .gitignore; then echo "PASS: .gitignore содержит правила для backup"; else echo "FAIL: .gitignore не содержит правил для backup"; exit 1; fi

---

ЗАДАНИЕ 2: Исправление блокирующих файловых операций

Приоритет: Высокий
Время: 30 минут
Файлы: services/memory.py, services/kv_store.py

Шаги выполнения:

1. Найти все синхронные файловые операции:
   Команда: grep -n "open(" services/memory.py services/kv_store.py
   Команда: grep -n "json.load" services/memory.py services/kv_store.py
   Команда: grep -n "json.dump" services/memory.py services/kv_store.py

2. Установить aiofiles:
   Команда: pip install aiofiles

3. Обновить requirements.txt:
   Добавить строку: aiofiles>=23.2.1

4. Рефакторинг services/memory.py:

   БЫЛО:
   import json
   from pathlib import Path

   async def load_facts(self, path: Path) -> list:
       if not path.exists():
           return []
       with open(path, 'r', encoding='utf-8') as f:
           return json.load(f)

   СТАЛО:
   import json
   from pathlib import Path
   import aiofiles

   async def load_facts(self, path: Path) -> list:
       if not path.exists():
           return []
       async with aiofiles.open(path, 'r', encoding='utf-8') as f:
           content = await f.read()
           return json.loads(content)

5. Рефакторинг services/kv_store.py: Аналогично заменить все open() на aiofiles.open().

Критерии успеха:
- Все open(), json.load(), json.dump() в async-функциях заменены на асинхронные аналоги
- Добавлен import aiofiles в измененные файлы
- aiofiles добавлен в requirements.txt
- Бот не блокирует event loop при чтении больших JSON-файлов

Тесты:

Создать файл test_async_io.py:
import ast
import sys

def check_sync_io_in_async(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        tree = ast.parse(f.read())

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        if child.func.id in ['open', 'json.load', 'json.dump']:
                            print(f"FAIL: Найдена синхронная операция {child.func.id} в async-функции (строка {child.lineno})")
                            return False
    return True

if not check_sync_io_in_async('services/memory.py'):
    sys.exit(1)
if not check_sync_io_in_async('services/kv_store.py'):
    sys.exit(1)

print("PASS: Все файловые операции в async-функциях асинхронные")

---

ЗАДАНИЕ 3: Надежный парсинг JSON от LLM

Приоритет: Высокий
Время: 45 минут
Файлы: services/kg_enricher.py, services/memory.py, создать services/json_parser.py

Шаги выполнения:

1. Создать утилиту services/json_parser.py:

import json
import re
from typing import Any, Union

def extract_json_from_text(text: str) -> Union[dict, list, None]:
    """
    Извлекает JSON из текста LLM, даже если он обернут в markdown или есть пояснения.
    """
    if not text:
        return None

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    markdown_pattern = r'```(?:json)?\s*([\s\S]*?)```'
    markdown_match = re.search(markdown_pattern, text, re.IGNORECASE)
    if markdown_match:
        try:
            return json.loads(markdown_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    json_obj_pattern = r'(\{[\s\S]*\}|\[[\s\S]*\])'
    json_match = re.search(json_obj_pattern, text)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def safe_parse_llm_json(text: str, expected_type: type = None) -> Any:
    """Безопасный парсер JSON от LLM с валидацией типа."""
    result = extract_json_from_text(text)

    if result is None:
        return None

    if expected_type and not isinstance(result, expected_type):
        return None

    return result

2. Обновить services/kg_enricher.py:

   БЫЛО:
   result = await self.ai_engine.generate(prompt)
   entities = json.loads(result)  # Может упасть!

   СТАЛО:
   from services.json_parser import safe_parse_llm_json

   result = await self.ai_engine.generate(prompt)
   entities = safe_parse_llm_json(result, expected_type=list)

   if entities is None:
       logger.warning(f"Не удалось распарсить JSON от LLM: {result[:200]}")
       return []

3. Обновить services/memory.py: Аналогично заменить json.loads() на safe_parse_llm_json().

Критерии успеха:
- Создан файл services/json_parser.py с функциями парсинга
- Все вызовы json.loads() для данных от LLM заменены на safe_parse_llm_json()
- Бот не падает при получении невалидного JSON от LLM
- Логируются предупреждения о неудачном парсинге

Тесты:

Создать файл test_json_parser.py:
import pytest
from services.json_parser import extract_json_from_text, safe_parse_llm_json

def test_clean_json():
    text = '{"entities": ["entity1", "entity2"]}'
    result = extract_json_from_text(text)
    assert result == {"entities": ["entity1", "entity2"]}

def test_markdown_json():
    text = '''
    Вот результат:
    ```json
    {"entities": ["entity1", "entity2"]}
    ```
    '''
    result = extract_json_from_text(text)
    assert result == {"entities": ["entity1", "entity2"]}

def test_json_with_explanation():
    text = '''
    Я извлек следующие сущности:
    {"entities": ["entity1", "entity2"]}
    Надеюсь, это поможет!
    '''
    result = extract_json_from_text(text)
    assert result == {"entities": ["entity1", "entity2"]}

def test_invalid_json():
    text = 'Извините, я не смог выполнить запрос'
    result = extract_json_from_text(text)
    assert result is None

def test_type_validation():
    text = '{"key": "value"}'
    result = safe_parse_llm_json(text, expected_type=list)
    assert result is None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

---

ЗАДАНИЕ 4: Безопасный парсинг веб-страниц

Приоритет: Средний
Время: 30 минут
Файлы: services/web_search.py

Шаги выполнения:

1. Проверить текущий метод парсинга:
   Команда: grep -A 10 "re.finditer" services/web_search.py

2. Установить selectolax (быстрый и безопасный):
   Команда: pip install selectolax

3. Обновить requirements.txt:
   Добавить строку: selectolax>=0.3.11

4. Рефакторинг парсинга:

   БЫЛО:
   import re

   for match in re.finditer(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
       url = match.group(1)
       title = re.sub(r'<[^>]+>', '', match.group(2))

   СТАЛО:
   from selectolax.parser import HTMLParser

   tree = HTMLParser(html)
   for node in tree.css('a[href]'):
       url = node.attributes.get('href', '')
       title = node.text(strip=True)

Критерии успеха:
- Все регулярные выражения для парсинга HTML заменены на selectolax
- selectolax добавлен в requirements.txt
- Парсинг работает быстрее и не ломается при изменении верстки

Тесты:

Создать файл test_web_search_parsing.py:
import pytest
from selectolax.parser import HTMLParser

def test_selectolax_parsing():
    html = '''
    <html>
        <body>
            <a href="https://example.com">Example Site</a>
            <a href="https://test.com">Test <b>Bold</b> Text</a>
        </body>
    </html>
    '''

    tree = HTMLParser(html)
    links = []
    for node in tree.css('a[href]'):
        url = node.attributes.get('href', '')
        title = node.text(strip=True)
        links.append({'url': url, 'title': title})

    assert len(links) == 2
    assert links[0]['url'] == 'https://example.com'
    assert links[0]['title'] == 'Example Site'
    assert links[1]['title'] == 'Test Bold Text'

def test_malformed_html():
    html = '<a href="https://example.com">Unclosed tag'
    tree = HTMLParser(html)
    links = list(tree.css('a[href]'))
    assert len(links) == 1

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

---

ЗАДАНИЕ 5: Внедрение векторного поиска

Приоритет: Высокий
Время: 2-3 часа
Файлы: создать services/vector_store.py, обновить services/memory.py

Шаги выполнения:

1. Предложить пользователю варианты:
   Варианты реализации векторного поиска:

   [1] Sentence-Transformers + ChromaDB (рекомендуется)
       Плюсы: Быстрый, локальный, хорошо интегрируется
       Минусы: Требует 500MB на модель
       Установка: pip install sentence-transformers chromadb

   [2] OpenAI Embeddings + Qdrant
       Плюсы: Высокое качество, не требует GPU
       Минусы: Платный API, зависимость от сети
       Установка: pip install openai qdrant-client

   [3] Ollama Embeddings (локально)
       Плюсы: Бесплатно, приватно
       Минусы: Медленно, требует ресурсов
       Установка: pip install ollama

   Какой вариант выбираем?

2. Дождаться выбора пользователя

3. Реализация для варианта [1] (Sentence-Transformers + ChromaDB):

   Команда установки: pip install sentence-transformers chromadb

   Создать services/vector_store.py:
   import chromadb
   from chromadb.config import Settings
   from sentence_transformers import SentenceTransformer
   from typing import List, Dict
   import logging

   logger = logging.getLogger(__name__)

   class VectorStore:
       def __init__(self, collection_name: str = "mempalace_facts"):
           self.client = chromadb.Client(Settings(
               chroma_db_impl="duckdb+parquet",
               persist_directory="./vector_db"
           ))

           self.collection = self.client.get_or_create_collection(
               name=collection_name,
               metadata={"hnsw:space": "cosine"}
           )

           logger.info("Загрузка модели эмбеддингов...")
           self.model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
           logger.info("Модель загружена")

       def add_facts(self, facts: List[Dict]) -> None:
           if not facts:
               return

           ids = [f"fact_{fact['id']}" for fact in facts]
           documents = [fact['text'] for fact in facts]
           metadatas = [fact.get('metadata', {}) for fact in facts]

           embeddings = self.model.encode(documents, convert_to_numpy=True).tolist()

           self.collection.add(
               ids=ids,
               embeddings=embeddings,
               documents=documents,
               metadatas=metadatas
           )

           logger.info(f"Добавлено {len(facts)} фактов в векторное хранилище")

       def search(self, query: str, top_k: int = 5) -> List[Dict]:
           query_embedding = self.model.encode([query], convert_to_numpy=True).tolist()[0]

           results = self.collection.query(
               query_embeddings=[query_embedding],
               n_results=top_k
           )

           formatted_results = []
           if results['documents'] and results['documents'][0]:
               for i, doc in enumerate(results['documents'][0]):
                   formatted_results.append({
                       'text': doc,
                       'score': results['distances'][0][i] if results['distances'] else 0,
                       'metadata': results['metadatas'][0][i] if results['metadatas'] else {}
                   })

           return formatted_results

       def delete_fact(self, fact_id: str) -> None:
           self.collection.delete(ids=[f"fact_{fact_id}"])
           logger.info(f"Удален факт {fact_id} из векторного хранилища")

4. Интеграция в services/memory.py:

   from services.vector_store import VectorStore

   class MemoryManager:
       def __init__(self):
           self.vector_store = VectorStore()

       async def search_facts(self, query: str, top_k: int = 5) -> List[Dict]:
           """Гибридный поиск: векторный + keyword"""
           vector_results = self.vector_store.search(query, top_k=top_k)
           keyword_results = await self._search_by_keywords(query)

           combined = vector_results + keyword_results

           seen = set()
           unique_results = []
           for result in combined:
               fact_id = result.get('metadata', {}).get('id')
               if fact_id and fact_id not in seen:
                   seen.add(fact_id)
                   unique_results.append(result)

           return unique_results[:top_k]

       async def add_fact(self, fact: Dict) -> None:
           await self._save_to_json(fact)
           self.vector_store.add_facts([fact])

Критерии успеха:
- Создан services/vector_store.py с интеграцией ChromaDB
- Векторное хранилище работает локально (папка ./vector_db)
- Поиск возвращает релевантные результаты по смыслу, а не только по словам
- Существующий keyword-поиск продолжает работать (гибридный режим)

Тесты:

Создать файл test_vector_store.py:
import pytest
from services.vector_store import VectorStore
import tempfile
import shutil

@pytest.fixture
def vector_store():
    temp_dir = tempfile.mkdtemp()
    store = VectorStore(collection_name="test_collection")
    yield store
    shutil.rmtree(temp_dir, ignore_errors=True)

def test_add_and_search(vector_store):
    facts = [
        {'id': 1, 'text': 'Python - это язык программирования'},
        {'id': 2, 'text': 'JavaScript используется для веб-разработки'},
        {'id': 3, 'text': 'Кофе - это напиток'},
    ]
    vector_store.add_facts(facts)

    results = vector_store.search("программирование", top_k=2)

    assert len(results) >= 1
    assert "Python" in results[0]['text'] or "язык" in results[0]['text']

def test_synonym_search(vector_store):
    facts = [
        {'id': 1, 'text': 'Я люблю читать книги'},
        {'id': 2, 'text': 'Мне нравится литература'},
    ]
    vector_store.add_facts(facts)

    results = vector_store.search("чтение", top_k=2)
    assert len(results) >= 1

def test_delete_fact(vector_store):
    facts = [{'id': 1, 'text': 'Test fact'}]
    vector_store.add_facts(facts)

    results_before = vector_store.search("test", top_k=1)
    assert len(results_before) > 0

    vector_store.delete_fact(1)

    results_after = vector_store.search("test", top_k=1)
    assert len(results_after) == 0 or 'Test fact' not in results_after[0]['text']

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

---

ИТОГОВЫЙ ЧЕК-ЛИСТ

После выполнения всех заданий агент ОБЯЗАН:

- Запустить все существующие тесты: pytest tests/ -v
- Запустить новые тесты из этого руководства
- Проверить отсутствие ошибок линтера: flake8 .
- Проверить отсутствие секретов в коде: python .git-hooks/check_no_secrets.py
- Запустить бота и проверить основные функции вручную
- Создать Git-коммит с описанием изменений
- Показать пользователю отчет о выполненных задачах

Отчет должен содержать:

## Отчет о выполненных задачах

### Выполнено:
1. Удалены backup-файлы (5 файлов)
2. Внедрен aiofiles для асинхронных файловых операций
3. Создан надежный парсер JSON от LLM
4. Заменен парсинг HTML регулярками на selectolax
5. Внедрен векторный поиск (ChromaDB + Sentence-Transformers)

### Результаты тестов:
- Пройдено: 45/45 тестов
- Покрытие кода: 78%
- Ошибок линтера: 0

### Следующие шаги (рекомендации):
1. Внедрить ReAct-паттерн для агентных функций
2. Добавить автономные фоновые задачи
3. Создать визуализацию графа знаний

### Внимание:
- Векторное хранилище занимает 500MB на диске
- Модель эмбеддингов загружается при первом запуске (30 сек)

---

ТРОУБЛШУТИНГ

Проблема: ChromaDB не устанавливается
Решение:
Команда: pip install --upgrade pip setuptools wheel
Команда: pip install chromadb

Проблема: Sentence-Transformers требует много памяти
Решение: Использовать меньшую модель:
self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')  # 80MB вместо 500MB

Проблема: aiofiles конфликтует с существующим кодом
Решение: Использовать asyncio.to_thread() как fallback:
async def load_facts(self, path: Path) -> list:
    if not path.exists():
        return []
    return await asyncio.to_thread(self._load_facts_sync, path)

def _load_facts_sync(self, path: Path) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

---

Конец руководства. Агент ОБЯЗАН следовать всем правилам и предлагать пользователю варианты выбора перед каждым критическим действием.
