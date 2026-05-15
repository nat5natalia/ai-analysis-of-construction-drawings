from pymongo import MongoClient
import sys
sys.path.insert(0, '/app')
from vector_db import vector_db
from ds import compute_embedding

print('Заполнение векторной БД...')

client = MongoClient('mongodb://drawing_mongo:27017/')
db = client['drawings_db']

drawings = list(db.drawings.find())
print(f'Найдено чертежей в MongoDB: {len(drawings)}')

if len(drawings) == 0:
    print('Нет чертежей в MongoDB! Сначала загрузите чертежи через API.')
    client.close()
    exit()

# Очищаем старую БД
vector_db._create_new()
print('Создана новая векторная БД')

count = 0
for drawing in drawings:
    drawing_id = drawing['id']
    filename = drawing['filename']
    description = drawing.get('description', '')
    
    text = f'{filename} {description}'[:1000]
    print(f'[{count+1}/{len(drawings)}] Добавление: {filename[:50]}...')
    
    try:
        embedding = compute_embedding(text)
        vector_db.add(drawing_id, embedding)
        count += 1
        print(f'   ✅ Добавлен (ID: {drawing_id[:8]}...)')
    except Exception as e:
        print(f'   ❌ Ошибка: {e}')

print(f'\n✅ Готово! Добавлено {count} чертежей')
print(f'Всего векторов в FAISS: {vector_db.index.ntotal}')
client.close()