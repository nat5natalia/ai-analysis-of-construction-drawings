import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
from collections import OrderedDict
from threading import Lock

logger = logging.getLogger(__name__)


class AgentCache:
    """
    Потокобезопасный LRU-кэш (Least Recently Used) с поддержкой TTL и хешированием.
    Автоматически вытесняет старые записи при достижении max_size.
    """

    def __init__(self, max_size: int = 500, default_ttl: int = 3600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        # OrderedDict используется для реализации LRU механики
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._lock = Lock()

        # Статистика для мониторинга
        self._hits = 0
        self._misses = 0

    def _generate_key(self, thread_id: str, path: str, question: str) -> str:
        """Создает стабильный MD5-хеш из параметров запроса."""
        raw_key = f"{thread_id}:{path}:{question}"
        return hashlib.md5(raw_key.encode()).hexdigest()

    def get(self, thread_id: str, path: str, question: str) -> Optional[Any]:
        """Получает значение из кэша с проверкой TTL."""
        key = self._generate_key(thread_id, path, question)

        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, expires_at = self._cache[key]

            # Проверка на "протухание" данных
            if time.time() > expires_at:
                del self._cache[key]
                self._misses += 1
                return None

            # Перемещаем в конец, как самый свежий (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, thread_id: str, path: str, question: str, value: Any, ttl: Optional[int] = None):
        """Сохраняет значение в кэш."""
        key = self._generate_key(thread_id, path, question)
        ttl = ttl or self.default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)

            self._cache[key] = (value, expires_at)

            # Если превышен размер, удаляем самый старый элемент (первый)
            if len(self._cache) > self.max_size:
                self._cache.popitem(last=False)

    def flush_to_log(self):
        """Сохраняет текущее состояние кэша на диск в JSON."""
        log_dir = Path("logs")
        try:
            log_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            cache_file = log_dir / f"cache_dump_{timestamp}.json"

            # Создаем копию данных для записи (чтобы не блокировать кэш надолго)
            with self._lock:
                data_to_save = {k: v[0] for k, v in self._cache.items()}

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)

            logger.info(f"Кэш успешно сброшен в {cache_file}")
        except Exception as e:
            logger.error(f"Ошибка при сохранении кэша: {e}")

    def clear(self):
        """Полная очистка кэша."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> Dict[str, Any]:
        """Возвращает статистику использования к[ш]а."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{(self._hits / total * 100):.1f}%" if total > 0 else "0%"
        }