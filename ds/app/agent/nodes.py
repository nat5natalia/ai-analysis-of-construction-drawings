from langchain_core.messages import SystemMessage

from app.prompts.agent import SYSTEM_AGENT


def node_agent(state, agent):

    messages = state["messages"]

    if not messages:
        messages = [
            SystemMessage(
                content=f"{SYSTEM_AGENT}\n\nТы работаешь со страницей: {state['page']}"
            )
        ]

    response = agent.invoke(messages)

    return {
        **state,
        "messages": messages + [response]
    }

def node_tools(state, tools):
    """
    Исполнение tool calls
    """

    last_message = state["messages"][-1]

    tool_messages = []

    for call in last_message.tool_calls:
        tool_name = call["name"]
        tool_args = call.get("args", {})

        tool = tools[tool_name]

        result = tool.invoke(tool_args)

        tool_messages.append(
            ToolMessage(
                content=str(result),
                tool_call_id=call["id"]
            )
        )

    return {
        **state,
        "messages": state["messages"] + tool_messages
    }


def node_retrieve(state, retriever):
    """
    Получение контекста
    """

    query = state.get("ocr_text", "")

    context = retriever(query)

    return {
        **state,
        "context": context
    }


def node_instructor(state, instructor_client):

    result = run_instructor(
        instructor_client,
        state,
        DrawingAnalysis
    )

    return {
        **state,
        "final_output": result
    }