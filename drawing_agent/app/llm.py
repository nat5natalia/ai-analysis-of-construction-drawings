from openai import OpenAI
from langchain_openai import ChatOpenAI
from omegaconf import DictConfig
from dotenv import load_dotenv
import os
load_dotenv()
def get_llm(cfg: DictConfig = None):
    model = 'qwen3.6-35b-32k'
    base_url = 'https://llm.ai-expert-opinion.ru/v1'
    temperature = 0.1
    max_tokens = 2000
    api_key = os.getenv("API_KEY")
    if cfg and hasattr(cfg, 'model'):
        model = cfg.model.get('name', model)
        base_url = cfg.model.get('base_url', base_url)
        temperature = cfg.model.get('temperature', temperature)
        max_tokens = cfg.model.get('max_tokens', max_tokens)
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=base_url,
        api_key=api_key,
        default_headers={
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "Drawing Agent"
        }
    )
    return llm