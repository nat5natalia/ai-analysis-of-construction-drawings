import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

class AgentCache:
    """
    Кэширует результаты обработки запросов.
    При завершении сессии flush_to_log() сохраняет весь кэш в JSON-файл.
    """
    def __init__(self):
        self._cache: Dict[str, Any] = {}

    def get(self, key: str) -> Optional[Dict]:
        return self._cache.get(key)

    def set(self, key: str, value: Dict):
        self._cache[key] = value

    def flush_to_log(self):
        """Сбрасывает весь кэш в лог-файл."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        cache_file = log_dir / f"cache_{timestamp}.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)
        self._cache.clear()
        print(f"Кэш сохранен в {cache_file}")