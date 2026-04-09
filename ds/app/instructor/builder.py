def build_instructor_input(state):
    ocr = state.get("ocr_text", "")
    context = state.get("context", "")
    messages = state.get("messages", [])

    last_message = ""
    if messages:
        last_message = messages[-1].content

    return f"""
    Страница: {state.get("page")}

    OCR:
    {state.get("ocr_text", "")}

    Контекст:
    {state.get("context", "")}

    Анализ агента:
    {state["messages"][-1].content if state["messages"] else ""}
    """