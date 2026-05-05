from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from app.state import AgentState
from app.nodes import preprocess_node, agent_node, tools_node, instructor_node, should_continue


def build_graph(cfg):
    workflow = StateGraph(AgentState)

    async def preprocess_with_cfg(state: AgentState):
        return await preprocess_node(state, cfg)

    async def agent_with_cfg(state: AgentState):
        return await agent_node(state, cfg)

    async def instruct_with_cfg(state: AgentState):
        return await instructor_node(state, cfg)

    def should_continue_with_cfg(state: AgentState):
        # should_continue обычно синхронная (логика условий)
        return should_continue(state, cfg)

    workflow.add_node("preprocess", preprocess_with_cfg)
    workflow.add_node("agent", agent_with_cfg)
    workflow.add_node("tools", tools_node)
    workflow.add_node('instructor', instruct_with_cfg)

    workflow.add_edge(START, "preprocess")
    workflow.add_edge("preprocess", "agent")

    use_instructor = cfg.run.get('use_instructor', True) if cfg and hasattr(cfg, 'run') else True

    if use_instructor:
        workflow.add_conditional_edges("agent", should_continue_with_cfg, {
            "tools": "tools",
            'instructor': 'instructor',
            "__end__": END
        })
        workflow.add_edge("tools", "agent")
        workflow.add_edge('instructor', END)
    else:
        workflow.add_conditional_edges("agent", should_continue_with_cfg, {
            "tools": "tools",
            "__end__": END
        })
        workflow.add_edge("tools", "agent")

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)