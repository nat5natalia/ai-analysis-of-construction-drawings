# app/graph.py
from langgraph.graph import StateGraph, END, START
from .state import AgentState
from .nodes import preprocess_node, agent_node, tools_node, instructor_node, should_continue


def build_graph(cfg, checkpointer=None):
    workflow = StateGraph(AgentState)

    # Обертки для узлов
    async def preprocess_with_cfg(state: AgentState):
        return await preprocess_node(state, cfg)

    async def agent_with_cfg(state: AgentState):
        return await agent_node(state, cfg)

    async def instruct_with_cfg(state: AgentState):
        return await instructor_node(state, cfg)

    # Добавление узлов
    workflow.add_node("preprocess", preprocess_with_cfg)
    workflow.add_node("agent", agent_with_cfg)
    workflow.add_node("tools", tools_node)
    workflow.add_node("instructor", instruct_with_cfg)

    # Линейные переходы
    workflow.add_edge(START, "preprocess")
    workflow.add_edge("preprocess", "agent")

    # Настройка условных переходов
    use_instructor = cfg.run.get('use_instructor', True)

    # ИСПРАВЛЕНИЕ: Добавляем поддержку обоих вариантов завершения
    # LangGraph часто возвращает именно "__end__"
    conditional_mapping = {
        "tools": "tools",
        "end": END,
        "__end__": END  # Добавлено для устранения KeyError
    }

    if use_instructor:
        conditional_mapping["instructor"] = "instructor"
    else:
        # Перенаправляем на выход, если инструктор отключен
        conditional_mapping["instructor"] = END

    workflow.add_conditional_edges(
        "agent",
        # Обертка для логирования (опционально, поможет отловить что именно возвращает функция)
        lambda state: should_continue(state, cfg),
        conditional_mapping
    )

    # Обратные петли и завершение
    workflow.add_edge("tools", "agent")

    if use_instructor:
        workflow.add_edge("instructor", END)

    return workflow.compile(checkpointer=checkpointer)