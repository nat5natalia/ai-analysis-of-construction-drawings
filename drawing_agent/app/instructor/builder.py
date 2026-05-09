def build_instructor_input(state):

    ocr = state.get("ocr_text", "")
    context = state.get("context", "")
    page = state.get("page", "unknown")
    heavy = state.get("heavy_analysis", "")
    messages = state.get("messages", [])

    last_message = ""
    if messages:
        for msg in reversed(messages):
            if hasattr(msg, "content") and isinstance(msg.content, str):
                last_message = msg.content
                break

    tool_results = ""
    if state.get("tool_results"):
        tool_results = "\n\n[РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ]\n"
        for tool_name, results in state["tool_results"].items():
            tool_results += f"\n{tool_name}:\n"
            for r in results[-3:]: 
                tool_results += f"  - {r[:200]}\n"

    return f"""
Ты получаешь данные анализа инженерного чертежа.

Страница: {page}

[OCR]
{ocr}
[ГЛУБОКИЙ ТЕКСТОВЫЙ ОТЧЕТ]
{heavy}
[Контекст]
{context}

[Анализ агента]
{last_message}
{tool_results}

Используй только эти данные.
"""
