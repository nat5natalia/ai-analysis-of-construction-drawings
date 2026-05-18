import os
import easyocr
from sentence_transformers import SentenceTransformer

def download_models():
    # Определение путей
    base_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.join(base_dir, "models")
    
    # 1. Загрузка EasyOCR (Детекция + RU/EN распознавание)
    print("--- Загрузка EasyOCR моделей ---")
    ocr_path = os.path.join(models_dir, "easyocr")
    os.makedirs(ocr_path, exist_ok=True)
    
    # Инициализация ридера принудительно скачивает модели в указанную папку
    reader = easyocr.Reader(['ru', 'en'], model_storage_directory=ocr_path, download_enabled=True)
    print(f"EasyOCR модели сохранены в: {ocr_path}")

    # 2. Загрузка Sentence Transformer
    print("\n--- Загрузка Sentence Transformer ---")
    transformer_path = os.path.join(models_dir, "transformers")
    os.makedirs(transformer_path, exist_ok=True)
    
    model_st = SentenceTransformer('all-MiniLM-L6-v2')
    model_st.save(transformer_path)
    print(f"Трансформер сохранен в: {transformer_path}")


if __name__ == "__main__":
    download_models()
