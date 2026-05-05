import time
import json
from pathlib import Path
from datetime import datetime

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"agent_{datetime.now().strftime('%Y%m%d')}.log"
ERROR_FILE = LOG_DIR / "errors.log"
HISTORY_FILE = LOG_DIR / "history.jsonl"


def init_clearml(project_name: str = None):
    return None


def log_to_clearml(text: str, level: str = "INFO"):
    log_entry = f"{level}: {text}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")
    if level == "ERROR":
        with open(ERROR_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")

def log_question_answer(question: str, answer: str, success: bool, response_time: float = None):
    entry = {
        "question": question[:500],
        "answer": answer[:1000] if answer else None,
        "success": success,
        "response_time": response_time
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False)
        f.write("\n")

def log_error(error: str, context: dict = None):
    error_entry = {
        "timestamp": datetime.now().isoformat(),
        "error": error,
        "context": context or {}
    }
    error_file = LOG_DIR / "errors.jsonl"
    with open(error_file, "a", encoding="utf-8") as f:
        json.dump(error_entry, f, ensure_ascii=False)
        f.write("\n")
    log_to_clearml(f"Ошибка: {error}", level="ERROR")

def log_metric(name: str, value: any):
    metric_entry = f" METRIC: {name} = {value}"
    metrics_file = LOG_DIR / f"metrics_{datetime.now().strftime('%Y%m%d')}.log"
    with open(metrics_file, "a", encoding="utf-8") as f:
        f.write(metric_entry + "\n")

def log_cache_operation(operation: str, key: str, success: bool):
    """Логирует операции с кэшем."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": operation,
        "key": key,
        "success": success
    }
    cache_log_file = LOG_DIR / "cache_operations.jsonl"
    with open(cache_log_file, "a", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False)
        f.write("\n")

def close_clearml():
    print(f"Логирование завершено.")
