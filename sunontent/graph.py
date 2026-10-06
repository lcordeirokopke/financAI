"""Monta o grafo LangGraph. A ordem das etapas, o fan-out e o retry ficam só aqui.

Etapas implementadas: E0 (coleta) e a entrada do modo --dev (referencia). As duas entradas
terminam o grafo até a E1 existir; quando ela for criada, ambas passam a seguir para ela.
"""

from langgraph.graph import END, START, StateGraph

from sunontent.nodes.coleta import coleta
from sunontent.nodes.referencia import referencia
from sunontent.schemas import PipelineState

K = 2  # orçamento de retry por célula; o valor lido no início do run entra no RunManifest


def escolher_entrada(state: PipelineState) -> str:
    """Modo normal entra pela E0; modo dev, pelo nó de referência."""
    return "referencia" if state.manifest.modo == "dev" else "coleta"


def construir_grafo(checkpointer=None):
    grafo = StateGraph(PipelineState)
    grafo.add_node("coleta", coleta)
    grafo.add_node("referencia", referencia)
    grafo.add_conditional_edges(START, escolher_entrada, ["coleta", "referencia"])
    grafo.add_edge("coleta", END)
    grafo.add_edge("referencia", END)
    return grafo.compile(checkpointer=checkpointer)
