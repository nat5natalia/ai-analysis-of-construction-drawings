import numpy as np
from sentence_transformers import SentenceTransformer

class EmbeddingGenerator:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.model = SentenceTransformer(model_name)

    def generate(self, text: str) -> np.ndarray:
        return self.model.encode(text)

    def batch_generate(self, texts: list) -> np.ndarray:
        return self.model.encode(texts)