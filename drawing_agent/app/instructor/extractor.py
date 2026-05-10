from app.prompts import SYSTEM_INSTRUCTOR
from app.instructor.builder import build_instructor_input
from app.llm import get_llm

async def run_instructor(state, schema):
    input_text = build_instructor_input(state)

    llm = get_llm()

    structured_llm = llm.with_structured_output(schema)
    messages = [
        ("system", SYSTEM_INSTRUCTOR),
        ("human", input_text)
    ]

    return await structured_llm.ainvoke(messages)