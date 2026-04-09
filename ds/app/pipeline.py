from app.data import load_drawing, preprocess
from app.tools import create_tools
from app.agent import build_graph
from app.instructor.client import get_instructor_client

def merge_results(results):
    """
    Объединяет результаты всех страниц
    """

    merged_objects = []
    merged_relationships = []

    for item in results:
        page_id = item["page"]
        res = item["result"]

        if not res:
            continue

        # объекты
        for obj in res.objects:
            obj.id = f"{page_id}_{obj.id}"  # уникализация
            merged_objects.append(obj)

        # связи
        for rel in res.relationships:
            rel.source_id = f"{page_id}_{rel.source_id}"
            rel.target_id = f"{page_id}_{rel.target_id}"
            merged_relationships.append(rel)

    return {
        "objects": merged_objects,
        "relationships": merged_relationships
    }

def run_pipeline(file_path, retriever):
    """
    Multi-page pipeline
    """

    # 1. загрузка (теперь список!)
    images = load_drawing(file_path)

    # 2. инициализация
    instructor_client = get_instructor_client()
    tools = create_tools()
    agent = create_agent()  # твоя функция
    graph = build_graph(agent, tools, instructor_client, retriever)

    results = []

    # 3. обработка КАЖДОЙ страницы
    for page_id, image in enumerate(images):

        data = preprocess(image)

        state = {
            "messages": [],
            "image_base64": data["image_base64"],
            "ocr_text": data["ocr_text"],
            "context": "",
            "page": page_id,
            "final_output": None
        }

        result = graph.invoke(state)

        results.append({
            "page": page_id,
            "result": result["final_output"]
        })

    # 4. объединение
    return merge_results(results)