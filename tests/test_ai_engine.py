"""Unit tests for services.ai_engine.

Covers config loading / current AI resolution, the synchronous call wrapper
(_sync_ai_call) for qwen/openai/gemini paths, the async executor wrapper and
the streaming generator.
"""

import asyncio
import builtins
import importlib
import json
import sys

import pytest

import services.ai_engine as ai_engine


@pytest.fixture(autouse=True)
def clear_cache():
    ai_engine.invalidate_ai_cache()
    yield
    ai_engine.invalidate_ai_cache()


@pytest.fixture(autouse=True)
def _no_real_ollama(monkeypatch):
    """Не допускаем реальный subprocess (ollama list/serve) в тестах."""
    monkeypatch.setattr(
        "services.ollama_process.ensure_ollama_running",
        lambda model="qwen2.5:7b": None,
    )


def _read_file(path) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


class FakeStreamMessage:
    def __init__(self, content):
        self.content = content


class FakeStreamChoice:
    def __init__(self, content=None, finish_reason="stop", delta=None):
        self.message = FakeStreamMessage(content)
        self.finish_reason = finish_reason
        self.delta = delta


class FakeSyncResponse:
    def __init__(self, content=None, finish_reason="stop"):
        self.choices = [FakeStreamChoice(content, finish_reason)]


class FakeCompletions:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._response


class FakeChat:
    def __init__(self, response):
        self.completions = FakeCompletions(response)


class FakeOpenAI:
    def __init__(self, response=None, base_url=None, api_key=None):
        self.base_url = base_url
        self.api_key = api_key
        self.chat = FakeChat(response)


class FakeDelta:
    def __init__(self, content=None):
        self.content = content


class FakeStreamChunk:
    def __init__(self, choices):
        self.choices = choices


class FakeStream:
    def __init__(self, chunks):
        self.chunks = chunks

    def __iter__(self):
        return iter(self.chunks)


class FakePart:
    def __init__(self, text):
        self.text = text


class FakeContent:
    def __init__(self, role, parts):
        self.role = role
        self.parts = parts


class FakeGenerateContentConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeGenAI:
    def __init__(self, response_text="gemini answer"):
        self.response_text = response_text

    class Client:
        def __init__(self, api_key=None):
            self.api_key = api_key
            self.calls = []
            self.response_text = "gemini answer"

        class _Models:
            def __init__(self, owner):
                self.owner = owner

            def generate_content(self, model, contents, config=None):
                self.owner.response_text = "gemini answer"
                return _FakeResponse(self.owner.response_text)

            def generate_content_stream(self, model, contents, config=None):
                return iter([_FakeChunkText("chunk1")])

        def models_attr(self):
            return self._Models(self)

        @property
        def models(self):
            return self._Models(self)

    def normalize_r(self):
        return self.response_text


class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeChunkText:
    def __init__(self, text):
        self.text = text


class FakeGenAITypes:
    @staticmethod
    def Part(text):
        return FakePart(text)

    @staticmethod
    def Content(role, parts):
        return FakeContent(role, parts)

    @staticmethod
    def GenerateContentConfig(**kwargs):
        return FakeGenerateContentConfig(**kwargs)


@pytest.fixture
def fake_models_config(tmp_path):
    def make(content):
        cfg = tmp_path / "models.json"
        cfg.write_text(json.dumps(content), encoding="utf-8")
        return cfg

    return make


# ---------- _load_models_config / get_current_ai / invalidate ----------


def test_load_models_config_returns_defaults_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(tmp_path / "nope.json"))
    assert _load() == {"ollama": [], "openai": [], "gemini": []}


def test_load_models_config_returns_defaults_on_invalid_json(monkeypatch, tmp_path):
    cfg = tmp_path / "models.json"
    cfg.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg))
    assert _load() == {"ollama": [], "openai": [], "gemini": []}


def test_load_models_config_parses_valid_json(monkeypatch, fake_models_config):
    cfg = fake_models_config({"ollama": [{"tag": "qwen2.5:7b"}]})
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg))
    assert _load() == {"ollama": [{"tag": "qwen2.5:7b"}]}


def _load():
    return ai_engine._load_models_config()


def test_get_current_ai_falls_back_to_gemini_default(monkeypatch, tmp_path):
    monkeypatch.setattr(
        ai_engine, "MODELS_CONFIG_PATH", str(tmp_path / "nope.json"),
    )
    monkeypatch.setattr(ai_engine, "CONFIG_AI_FILE", str(tmp_path / "nope.conf"))
    assert ai_engine.get_current_ai() == ("gemini", "gemini-flash-latest")


def test_get_current_ai_reads_tag_from_file(monkeypatch, tmp_path, fake_models_config):
    cfg = fake_models_config({"gemini": [{"tag": "gemini-pro"}]})
    conf = tmp_path / ".current_ai"
    conf.write_text("gemini-pro", encoding="utf-8")
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg))
    monkeypatch.setattr(ai_engine, "CONFIG_AI_FILE", str(conf))
    assert ai_engine.get_current_ai() == ("gemini", "gemini-pro")


def test_get_current_ai_maps_ollama_to_qwen(monkeypatch, tmp_path, fake_models_config):
    cfg = fake_models_config({"ollama": [{"tag": "qwen2.5:7b"}]})
    conf = tmp_path / ".current_ai"
    conf.write_text("qwen2.5:7b", encoding="utf-8")
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg))
    monkeypatch.setattr(ai_engine, "CONFIG_AI_FILE", str(conf))
    assert ai_engine.get_current_ai() == ("qwen", "qwen2.5:7b")


def test_get_current_ai_openai_engine(monkeypatch, tmp_path, fake_models_config):
    cfg = fake_models_config({"openai": [{"tag": "gpt-4o"}]})
    conf = tmp_path / ".current_ai"
    conf.write_text("gpt-4o", encoding="utf-8")
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg))
    monkeypatch.setattr(ai_engine, "CONFIG_AI_FILE", str(conf))
    assert ai_engine.get_current_ai() == ("openai", "gpt-4o")


def test_get_current_ai_falls_back_when_tag_unknown(
    monkeypatch, tmp_path, fake_models_config,
):
    cfg = fake_models_config({"gemini": [{"tag": "gemini-pro"}]})
    conf = tmp_path / ".current_ai"
    conf.write_text("unknown-tag", encoding="utf-8")
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg))
    monkeypatch.setattr(ai_engine, "CONFIG_AI_FILE", str(conf))
    assert ai_engine.get_current_ai() == ("gemini", "unknown-tag")


def test_get_current_ai_handles_read_error(monkeypatch, tmp_path, fake_models_config):
    cfg = fake_models_config({"gemini": [{"tag": "gemini-pro"}]})
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg))
    monkeypatch.setattr(ai_engine, "CONFIG_AI_FILE", str(tmp_path / "nope.conf"))
    assert ai_engine.get_current_ai() == ("gemini", "gemini-flash-latest")


def test_invalidate_ai_cache_clears_cached_config(
    monkeypatch, tmp_path, fake_models_config,
):
    cfg1 = fake_models_config({"ollama": [{"tag": "a"}]})
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg1))
    assert _load()["ollama"] == [{"tag": "a"}]

    cfg2 = tmp_path / "models2.json"
    cfg2.write_text(json.dumps({"ollama": [{"tag": "b"}]}), encoding="utf-8")
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg2))
    ai_engine.invalidate_ai_cache()
    assert _load()["ollama"] == [{"tag": "b"}]


# ---------- _sync_ai_call: qwen ----------


def test_sync_qwen_returns_cleaned_response(monkeypatch):
    fake = FakeOpenAI(FakeSyncResponse("Привет!"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "qwen2.5:7b", [{"role": "user", "content": "hi"}])
    assert out == "Привет!"


def test_sync_qwen_preserves_system_message_from_messages(monkeypatch):
    fake = FakeOpenAI(FakeSyncResponse("ok"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    msgs = [
        {"role": "system", "content": "CUSTOM_SYSTEM"},
        {"role": "user", "content": "hi"},
    ]
    ai_engine._sync_ai_call("qwen", "m", msgs, context="ctx", user_query="q")
    sent = fake.chat.completions.last_kwargs["messages"]
    assert sent[0] == {"role": "system", "content": "CUSTOM_SYSTEM"}
    assert sent[0] != {"role": "system", "content": "Ты — полезный ассистент."}


def test_sync_qwen_generates_system_prompt_without_one(monkeypatch):
    fake = FakeOpenAI(FakeSyncResponse("ok"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    sent = fake.chat.completions.last_kwargs["messages"]
    assert sent[0]["role"] == "system"
    assert sent[0]["content"].strip()


def test_sync_qwen_embeds_images_in_first_user_message(monkeypatch):
    class CustomOpenAI(FakeOpenAI):
        def __init__(self, base_url=None, api_key=None):
            super().__init__(FakeSyncResponse("ok"), base_url, api_key)

    instance = CustomOpenAI()
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: instance)
    msgs = [
        {"role": "user", "content": "look"},
        {"role": "user", "content": "second"},
    ]
    ai_engine._sync_ai_call(
        "qwen", "m", msgs, images=["YmluYXJ5=="],
    )
    sent = instance.chat.completions.last_kwargs["messages"]
    assert isinstance(sent, list)
    user_msg = [m for m in sent if m["role"] == "user"][0]
    assert user_msg["content"] == [
        {"type": "text", "text": "look"},
        {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64,YmluYXJ5=="},
        },
    ]
    assert "YmluYXJ5==" not in _content_of_second(sent)


def _content_of_second(msgs):
    return " ".join(
        m.get("content", "") if isinstance(m.get("content"), str) else ""
        for m in msgs
    )


def test_sync_qwen_empty_response(monkeypatch):
    fake = FakeOpenAI(FakeSyncResponse(None))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert out == "❌ Пустой ответ от Ollama."


def test_sync_qwen_no_choices_field(monkeypatch):
    class NoChoicesResponse:
        pass

    fake = FakeOpenAI(NoChoicesResponse())
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert "Ошибка ИИ" in out


def test_sync_qwen_truncated_by_length(monkeypatch):
    fake = FakeOpenAI(FakeSyncResponse("   ", finish_reason="length"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert out == "❌ Ответ был обрезан из-за лимита токенов."


def test_sync_qwen_no_text_finish_reason(monkeypatch):
    fake = FakeOpenAI(FakeSyncResponse("  ", finish_reason="stop"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert "без текста" in out


def test_sync_qwen_strips_thinking_tags(monkeypatch):
    raw = (
        "Привет!\n"
        "Умные вещи\n"
        "Имя ответа"
    )
    fake = FakeOpenAI(FakeSyncResponse(raw))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert "Привет!" in out


def test_sync_qwen_strips_chatml_tokens(monkeypatch):
    raw = "Ответ<|im_end|>мусор"
    fake = FakeOpenAI(FakeSyncResponse(raw))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert out == "Ответ"


def test_sync_qwen_trims_user_echo(monkeypatch):
    raw = "Текст ответа\nuser: следующий вопрос"
    fake = FakeOpenAI(FakeSyncResponse(raw))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert out == "Текст ответа"


def test_sync_qwen_strips_trailing_chinese(monkeypatch):
    raw = "Текст" + "了" * 10
    fake = FakeOpenAI(FakeSyncResponse(raw))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert out == "Текст"


def test_sync_qwen_import_error(monkeypatch):
    monkeypatch.setattr(ai_engine, "OpenAI", None)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert "Библиотека openai" in out


def test_sync_qwen_network_error(monkeypatch):
    class BoomOpenAI(FakeOpenAI):
        def __init__(self, base_url=None, api_key=None):
            super().__init__(FakeStreamChoice("x"), base_url, api_key)
            self.chat.completions = _BoomCompletions()

    class _BoomCompletions:
        def create(self, **kwargs):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: BoomOpenAI(**kwargs))
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert "Ошибка ИИ" in out
    assert "connection refused" in out


def test_sync_qwen_ensures_ollama_running(monkeypatch):
    calls = []

    def fake_ensure(model="qwen2.5:7b"):
        calls.append(model)

    monkeypatch.setattr("services.ollama_process.ensure_ollama_running", fake_ensure)
    fake = FakeOpenAI(FakeSyncResponse("Привет"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert calls == ["m"]
    assert out == "Привет"


def test_sync_qwen_ensure_failure_friendly_message(monkeypatch):
    def boom(model="qwen2.5:7b"):
        raise RuntimeError("Ollama CLI not found")

    monkeypatch.setattr("services.ollama_process.ensure_ollama_running", boom)
    fake = FakeOpenAI(FakeSyncResponse("не должен вернуться"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert "Не удалось подключиться к Ollama" in out
    assert "Ollama CLI not found" not in out
    assert "не должен вернуться" not in out


def test_sync_qwen_apiconnection_error_friendly_message(monkeypatch):
    class APIConnectionError(Exception):
        pass

    class BoomCompletions:
        def create(self, **kwargs):
            raise APIConnectionError("Connection error.")

    class BoomOpenAI(FakeOpenAI):
        def __init__(self, base_url=None, api_key=None):
            super().__init__(None, base_url, api_key)
            self.chat.completions = BoomCompletions()

    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: BoomOpenAI(**kwargs))
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert "Не удалось подключиться к Ollama" in out
    assert "Запустите Ollama" in out


def test_sync_gemini_does_not_ensure_ollama(monkeypatch):
    def fake_ensure(model="qwen2.5:7b"):
        raise AssertionError("ensure_ollama_running вызван для gemini")

    monkeypatch.setattr("services.ollama_process.ensure_ollama_running", fake_ensure)
    monkeypatch.setenv("GEMINI_API_KEY", "rk-test")
    monkeypatch.setattr(ai_engine, "genai", FakeGenAI)
    monkeypatch.setattr(ai_engine, "genai_types", FakeGenAITypes)
    out = ai_engine._sync_ai_call(
        "gemini", "gemini-pro", [{"role": "user", "content": "hi"}],
    )
    assert out == "gemini answer"


def test_sync_openai_does_not_ensure_ollama(monkeypatch):
    def fake_ensure(model="qwen2.5:7b"):
        raise AssertionError("ensure_ollama_running вызван для openai")

    monkeypatch.setattr("services.ollama_process.ensure_ollama_running", fake_ensure)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake = FakeOpenAI(FakeSyncResponse("openai answer"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call(
        "openai", "gpt-4o", [{"role": "user", "content": "hi"}],
    )
    assert out == "openai answer"


# ---------- _is_ollama_unavailable ----------


def test_is_ollama_unavailable_true_for_connection_classes():
    class APIConnectionError(Exception):
        pass

    class ConnectError(Exception):
        pass

    class ConnectTimeout(Exception):
        pass

    for exc in (
        APIConnectionError("boom"),
        ConnectError("boom"),
        ConnectTimeout("boom"),
    ):
        assert ai_engine._is_ollama_unavailable(exc) is True


def test_is_ollama_unavailable_true_for_autostart_runtime_error():
    err = RuntimeError(
        "Не удалось подключиться к Ollama (localhost:11434). Ollama CLI not found",
    )
    assert ai_engine._is_ollama_unavailable(err) is True


def test_is_ollama_unavailable_false_for_other_errors():
    class OtherError(Exception):
        pass

    assert ai_engine._is_ollama_unavailable(RuntimeError("connection refused")) is False
    assert ai_engine._is_ollama_unavailable(ValueError("Ollama broken")) is False
    assert ai_engine._is_ollama_unavailable(OtherError("connect")) is False
    assert ai_engine._is_ollama_unavailable(ImportError("no lib")) is False


# ---------- _sync_ai_call: openai ----------


def test_sync_openai_missing_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: FakeOpenAI())
    out = ai_engine._sync_ai_call("openai", "gpt-4o", [{"role": "user", "content": "hi"}])
    assert "OPENAI_API_KEY" in out


def test_sync_openai_success(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake = FakeOpenAI(FakeSyncResponse("openai answer"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call(
        "openai", "gpt-4o", [{"role": "user", "content": "hi"}],
    )
    assert out == "openai answer"


def test_sync_openai_import_error(monkeypatch):
    monkeypatch.setattr(ai_engine, "OpenAI", None)
    out = ai_engine._sync_ai_call(
        "openai", "gpt-4o", [{"role": "user", "content": "hi"}],
    )
    assert "Библиотека openai" in out


# ---------- _sync_ai_call: gemini ----------


def test_sync_gemini_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(ai_engine, "genai", FakeGenAI)
    monkeypatch.setattr(ai_engine, "genai_types", FakeGenAITypes)
    out = ai_engine._sync_ai_call("gemini", "gemini-pro", [{"role": "user", "content": "hi"}])
    assert "GEMINI_API_KEY" in out


def test_sync_gemini_success(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "rk-test")
    monkeypatch.setattr(ai_engine, "genai", FakeGenAI)
    monkeypatch.setattr(ai_engine, "genai_types", FakeGenAITypes)
    out = ai_engine._sync_ai_call(
        "gemini", "gemini-pro", [{"role": "user", "content": "hi"}],
    )
    assert out == "gemini answer"


def test_sync_gemini_import_error(monkeypatch):
    monkeypatch.setattr(ai_engine, "genai", None)
    out = ai_engine._sync_ai_call(
        "gemini", "gemini-pro", [{"role": "user", "content": "hi"}],
    )
    assert "google-genai" in out


# ---------- _sync_ai_call: unknown engine ----------


def test_sync_unknown_engine(monkeypatch):
    out = ai_engine._sync_ai_call("tpu", "m", [{"role": "user", "content": "hi"}])
    assert "Неизвестный движок" in out
    assert "tpu" in out


# ---------- get_ai_response_async ----------


def test_get_ai_response_async_success(monkeypatch):
    monkeypatch.setattr(ai_engine, "_sync_ai_call", lambda *a, **k: "sync ok")
    out = asyncio.run(
        ai_engine.get_ai_response_async("qwen", "m", [{"role": "user", "content": "hi"}]),
    )
    assert out == "sync ok"


def test_get_ai_response_async_executor_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("executor exploded")

    monkeypatch.setattr(ai_engine, "_sync_ai_call", boom)
    out = asyncio.run(
        ai_engine.get_ai_response_async("qwen", "m", [{"role": "user", "content": "hi"}]),
    )
    assert "Системная ошибка" in out
    assert "executor exploded" in out


# ---------- stream_ai_response_async ----------


def _collect_stream_kwargs(monkeypatch, engine, model, messages, **kwargs):
    chunks = []

    async def collect():
        async for ch in ai_engine.stream_ai_response_async(
            engine, model, messages, **kwargs,
        ):
            chunks.append(ch)

    asyncio.run(collect())
    return chunks


def test_stream_qwen_yields_cleaned_chunks(monkeypatch):
    stream = FakeStream(
        [
            FakeStreamChunk([FakeStreamChoice(delta=FakeDelta("Привет "))]),
            FakeStreamChunk([FakeStreamChoice(delta=FakeDelta("мир"))]),
            FakeStreamChunk([]),
        ],
    )
    fake = FakeOpenAI(stream)
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = _collect_stream_kwargs(
        monkeypatch, "qwen", "m", [{"role": "user", "content": "hi"}],
    )
    assert out == ["Привет ", "мир"]


def test_stream_qwen_embeds_images(monkeypatch):
    stream = FakeStream(
        [FakeStreamChunk([FakeStreamChoice(delta=FakeDelta("с картинкой"))])],
    )
    fake = FakeOpenAI(stream)
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = _collect_stream_kwargs(
        monkeypatch, "qwen", "m",
        [{"role": "user", "content": "op", "name": "x"}],
        images=["aW1n"],
    )
    assert out == ["с картинкой"]


def test_stream_qwen_import_error_chunk(monkeypatch):
    monkeypatch.setattr(ai_engine, "OpenAI", None)
    out = _collect_stream_kwargs(
        monkeypatch, "qwen", "m", [{"role": "user", "content": "hi"}],
    )
    assert len(out) == 1
    assert "Ошибка стриминга" in out[0]
    assert "Библиотека openai" in out[0]


def test_stream_qwen_ensures_ollama_running(monkeypatch):
    calls = []

    def fake_ensure(model="qwen2.5:7b"):
        calls.append(model)

    monkeypatch.setattr("services.ollama_process.ensure_ollama_running", fake_ensure)
    stream = FakeStream(
        [FakeStreamChunk([FakeStreamChoice(delta=FakeDelta("ok"))])],
    )
    fake = FakeOpenAI(stream)
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = _collect_stream_kwargs(
        monkeypatch, "qwen", "m", [{"role": "user", "content": "hi"}],
    )
    assert calls == ["m"]
    assert out == ["ok"]


def test_stream_qwen_ensure_failure_friendly_chunk(monkeypatch):
    def boom(model="qwen2.5:7b"):
        raise RuntimeError("Ollama server did not start in time")

    monkeypatch.setattr("services.ollama_process.ensure_ollama_running", boom)
    out = _collect_stream_kwargs(
        monkeypatch, "qwen", "m", [{"role": "user", "content": "hi"}],
    )
    assert len(out) == 1
    assert "Не удалось подключиться к Ollama" in out[0]


def test_stream_openai_missing_key_chunk(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: FakeOpenAI())
    out = _collect_stream_kwargs(
        monkeypatch, "openai", "gpt-4o", [{"role": "user", "content": "hi"}],
    )
    assert len(out) == 1
    assert "OPENAI_API_KEY" in out[0]


def test_stream_openai_yields_chunks(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    stream = FakeStream([FakeStreamChunk([FakeStreamChoice(delta=FakeDelta("данные"))])])
    fake = FakeOpenAI(stream)
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = _collect_stream_kwargs(
        monkeypatch, "openai", "gpt-4o", [{"role": "user", "content": "hi"}],
    )
    assert out == ["данные"]


def test_stream_gemini_yields_chunks(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "rk-test")
    monkeypatch.setattr(ai_engine, "genai", FakeGenAI)
    monkeypatch.setattr(ai_engine, "genai_types", FakeGenAITypes)
    out = _collect_stream_kwargs(
        monkeypatch, "gemini", "gemini-pro", [{"role": "user", "content": "hi"}],
    )
    assert out == ["chunk1"]


def test_stream_gemini_import_error_chunk(monkeypatch):
    monkeypatch.setattr(ai_engine, "genai", None)
    out = _collect_stream_kwargs(
        monkeypatch, "gemini", "gemini-pro", [{"role": "user", "content": "hi"}],
    )
    assert len(out) == 1
    assert "Ошибка стриминга" in out[0]


def test_stream_runtime_error_chunk(monkeypatch):
    class BoomStream(FakeStream):
        def __iter__(self):
            raise RuntimeError("stream broke")

    fake = FakeOpenAI(BoomStream([]))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = _collect_stream_kwargs(
        monkeypatch, "qwen", "m", [{"role": "user", "content": "hi"}],
    )
    assert len(out) == 1
    assert "Ошибка стриминга" in out[0]
    assert "stream broke" in out[0]


# ---------- import fallbacks ----------


def test_stream_unknown_engine_yields_nothing(monkeypatch):
    out = _collect_stream_kwargs(
        monkeypatch, "tpu", "m", [{"role": "user", "content": "hi"}],
    )
    assert out == []


def test_stream_gemini_skips_empty_text_chunk(monkeypatch):
    class FakeGenAI3:
        class Client:
            def __init__(self, api_key=None):
                self.api_key = api_key

            class _Models:
                def __init__(self, owner):
                    self.owner = owner

                def generate_content_stream(self, model, contents, config=None):
                    return iter([_FakeChunkText(""), _FakeChunkText("раз")])

            @property
            def models(self):
                return self._Models(self)

    monkeypatch.setenv("GEMINI_API_KEY", "rk-test")
    monkeypatch.setattr(ai_engine, "genai", FakeGenAI3)
    monkeypatch.setattr(ai_engine, "genai_types", FakeGenAITypes)
    out = _collect_stream_kwargs(
        monkeypatch, "gemini", "gemini-pro", [{"role": "user", "content": "hi"}],
    )
    assert out == ["раз"]


def test_module_import_fallback_without_openai(monkeypatch):
    real_import = builtins.__import__

    def guarded(name, *a, **k):
        if name == "openai":
            raise ImportError("no openai")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guarded)
    importlib.reload(ai_engine)
    assert ai_engine.OpenAI is None
    monkeypatch.undo()
    importlib.reload(ai_engine)
    assert ai_engine.OpenAI is not None


def test_module_import_fallback_without_genai(monkeypatch):
    real_import = builtins.__import__

    def guarded(name, *a, **k):
        if name == "google":
            raise ImportError("no genai")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guarded)
    importlib.reload(ai_engine)
    assert ai_engine.genai is None
    monkeypatch.undo()
    importlib.reload(ai_engine)
    assert ai_engine.genai is not None


# ---------- extra branches ----------


def test_get_current_ai_handles_read_error_on_directory(monkeypatch, tmp_path, fake_models_config):
    cfg = fake_models_config({"gemini": [{"tag": "gemini-pro"}]})
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg))
    monkeypatch.setattr(ai_engine, "CONFIG_AI_FILE", str(tmp_path))
    assert ai_engine.get_current_ai() == ("gemini", "gemini-flash-latest")


def test_get_current_ai_handles_empty_config_file(monkeypatch, tmp_path, fake_models_config):
    cfg = fake_models_config({"gemini": [{"tag": "gemini-pro"}]})
    monkeypatch.setattr(ai_engine, "MODELS_CONFIG_PATH", str(cfg))
    empty_file = tmp_path / "ai.conf"
    empty_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(ai_engine, "CONFIG_AI_FILE", str(empty_file))
    assert ai_engine.get_current_ai() == ("gemini", "gemini-flash-latest")


def test_sync_ollama_engine_normalized_to_qwen(monkeypatch):
    fake = FakeOpenAI(FakeSyncResponse("ok"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call(
        "OLLAMA", "m", [{"role": "user", "content": "hi"}],
    )
    assert out == "ok"


def test_sync_get_smart_prompt_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "services.prompts", None)
    fake = FakeOpenAI(FakeSyncResponse("ok"))
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = ai_engine._sync_ai_call("qwen", "m", [{"role": "user", "content": "hi"}])
    assert out == "ok"


def test_stream_ollama_normalized_to_qwen(monkeypatch):
    stream = FakeStream([FakeStreamChunk([FakeStreamChoice(delta=FakeDelta("х"))])])
    fake = FakeOpenAI(stream)
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = _collect_stream_kwargs(
        monkeypatch, "ollama", "m", [{"role": "user", "content": "hi"}],
    )
    assert out == ["х"]


def test_stream_get_smart_prompt_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "services.prompts", None)
    stream = FakeStream([FakeStreamChunk([FakeStreamChoice(delta=FakeDelta("ч"))])])
    fake = FakeOpenAI(stream)
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = _collect_stream_kwargs(
        monkeypatch, "qwen", "m", [{"role": "user", "content": "hi"}],
    )
    assert out == ["ч"]


def test_stream_qwen_skips_think_only_chunk(monkeypatch):
    stream = FakeStream(
        [
            FakeStreamChunk(
                [FakeStreamChoice(delta=FakeDelta("<think>размышление</think>"))],
            ),
            FakeStreamChunk([FakeStreamChoice(delta=FakeDelta("ответ"))]),
        ],
    )
    fake = FakeOpenAI(stream)
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = _collect_stream_kwargs(
        monkeypatch, "qwen", "m", [{"role": "user", "content": "hi"}],
    )
    assert out == ["ответ"]


def test_stream_openai_import_error_chunk(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(ai_engine, "OpenAI", None)
    out = _collect_stream_kwargs(
        monkeypatch, "openai", "gpt-4o", [{"role": "user", "content": "hi"}],
    )
    assert len(out) == 1
    assert "Библиотека openai" in out[0]


def test_stream_openai_skips_empty_delta(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    stream = FakeStream(
        [
            FakeStreamChunk([FakeStreamChoice(delta=FakeDelta(""))]),
            FakeStreamChunk([FakeStreamChoice(delta=FakeDelta("данные"))]),
        ],
    )
    fake = FakeOpenAI(stream)
    monkeypatch.setattr(ai_engine, "OpenAI", lambda **kwargs: fake)
    out = _collect_stream_kwargs(
        monkeypatch, "openai", "gpt-4o", [{"role": "user", "content": "hi"}],
    )
    assert out == ["данные"]


def test_stream_gemini_missing_key_chunk(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(ai_engine, "genai", FakeGenAI)
    monkeypatch.setattr(ai_engine, "genai_types", FakeGenAITypes)
    out = _collect_stream_kwargs(
        monkeypatch, "gemini", "gemini-pro", [{"role": "user", "content": "hi"}],
    )
    assert len(out) == 1
    assert "GEMINI_API_KEY" in out[0]


def test_stream_gemini_yields_multiple_chunks(monkeypatch):
    class FakeGenAI2:
        class Client:
            def __init__(self, api_key=None):
                self.api_key = api_key

            class _Models:
                def __init__(self, owner):
                    self.owner = owner

                def generate_content_stream(self, model, contents, config=None):
                    return iter([_FakeChunkText("раз"), _FakeChunkText("два")])

            @property
            def models(self):
                return self._Models(self)

    monkeypatch.setenv("GEMINI_API_KEY", "rk-test")
    monkeypatch.setattr(ai_engine, "genai", FakeGenAI2)
    monkeypatch.setattr(ai_engine, "genai_types", FakeGenAITypes)
    out = _collect_stream_kwargs(
        monkeypatch, "gemini", "gemini-pro", [{"role": "user", "content": "hi"}],
    )
    assert out == ["раз", "два"]
