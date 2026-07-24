"""
whisper_service.py
Глобальный singleton-сервис для faster-whisper.
Модели загружаются один раз при старте и переиспользуются.
"""
import logging
from functools import lru_cache

logger = logging.getLogger("WhisperService")

@lru_cache(maxsize=2)
def _load_model(model_size: str):
    logger.info(f"Loading whisper model '{model_size}'...")
    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device="cpu", compute_type="int8")

def get_whisper(model_size: str = "base"):
    """Возвращает кэшированную модель Whisper.
    model_size: 'base' (быстрая) или 'small' (точная)."""
    return _load_model(model_size)

def prewarm():
    """Предзагрузка моделей при старте бота."""
    logger.info("Pre-warming whisper model 'base'...")
    _load_model("base")
    logger.info("Whisper model 'base' loaded.")
