from openai import OpenAI
from langchain_openai import ChatOpenAI
from omegaconf import DictConfig
from dotenv import load_dotenv
import os
load_dotenv()


def get_api_key():
    api_key_file = os.getenv("OPENAI_API_KEY_FILE")
    if api_key_file and os.path.exists(api_key_file):
        with open(api_key_file, "r", encoding="utf-8") as file:
            return file.read().strip()
    return os.getenv("OPENAI_API_KEY")


def get_model_name(model_cfg, default: str) -> str:
    return model_cfg.get("name") or model_cfg.get("model") or default


def get_llm(cfg: DictConfig = None):
    model = 'qwen3.6-35b-32k'
    base_url = 'https://llm.ai-expert-opinion.ru/v1'
    temperature = 0.1
    max_tokens = 2000
    timeout = 120
    max_retries = 2
    api_key = get_api_key()
    if cfg and hasattr(cfg, 'model'):
        model = get_model_name(cfg.model, model)
        base_url = cfg.model.get('base_url', base_url)
        temperature = cfg.model.get('temperature', temperature)
        max_tokens = cfg.model.get('max_tokens', max_tokens)
        timeout = cfg.model.get('timeout', timeout)
        max_retries = cfg.model.get('max_retries', max_retries)
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
        streaming=False,
        default_headers={
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "Drawing Agent"
        }
    )
    return llm
