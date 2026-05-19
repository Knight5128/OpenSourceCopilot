"""Eight-node LangGraph DAG that produces an OnboardingPlan.

    SkillExtractor → RepoMatcher → IssueFinder → FriendlinessRanker
                  → PathPredictor → SimilarPRRetriever → DifficultyEstimator
                  → PRDrafter

Member C owns this file. Each node is implemented in `nodes.py` (TODO).
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph


class AgentState(TypedDict, total=False):
    skills: list[str]
    direction: str
    hours_per_week: int
    candidate_repos: list[dict]
    selected_repo: dict
    issues: list[dict]
    plan: dict
    trace: list[dict]


def build_graph():
    g = StateGraph(AgentState)

    # --- Placeholder nodes; real implementations land in nodes.py ---
    def todo(name: str):
        def _inner(state: AgentState) -> AgentState:
            state.setdefault("trace", []).append({"node": name, "status": "todo"})
            return state

        _inner.__name__ = name
        return _inner

    for node in [
        "SkillExtractor",
        "RepoMatcher",
        "IssueFinder",
        "FriendlinessRanker",
        "PathPredictor",
        "SimilarPRRetriever",
        "DifficultyEstimator",
        "PRDrafter",
    ]:
        g.add_node(node, todo(node))

    g.set_entry_point("SkillExtractor")
    g.add_edge("SkillExtractor", "RepoMatcher")
    g.add_edge("RepoMatcher", "IssueFinder")
    g.add_edge("IssueFinder", "FriendlinessRanker")
    g.add_edge("FriendlinessRanker", "PathPredictor")
    g.add_edge("PathPredictor", "SimilarPRRetriever")
    g.add_edge("SimilarPRRetriever", "DifficultyEstimator")
    g.add_edge("DifficultyEstimator", "PRDrafter")
    g.add_edge("PRDrafter", END)

    return g.compile()
