import os
import json
from typing import TypedDict, Dict, Any, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage

# We dynamically import the required LLM interface
try:
    from langchain_ollama import ChatOllama
    from langchain_openai import ChatOpenAI
except ImportError:
    pass  # We assume the caller handles environment dependencies correctly

def get_llm(model_name: str = None):
    """
    Model Factory based on environment variables or GPU availability.
    If ENV_TYPE=gcp_pod (or has GPU), it assumes vLLM/OpenAI endpoint is available.
    Otherwise, defaults to local Ollama (local_cpu).
    """
    env_type = os.environ.get("ENV_TYPE", "local_cpu")
    
    if env_type == "gcp_pod":
        # Assume a vLLM server is running on the pod, exposing an OpenAI-compatible API
        api_base = os.environ.get("DEEPSEEK_API_URL", "http://localhost:8000/v1")
        return ChatOpenAI(
            model=model_name or "deepseek-r1",
            openai_api_base=api_base,
            openai_api_key="not-needed"
        )
    else:
        # Default to local Ollama (e.g. deepseek-r1-distill-qwen-14b or similar)
        return ChatOllama(model=model_name or "qwen2.5-coder:1.5b", temperature=0.1)

class ReviewState(TypedDict):
    solution_text: str
    problem_text: str
    domain: str
    thoughts: List[str]
    anomalies: List[str]
    final_verdict: str

def call_llm(prompt: str) -> str:
    llm = get_llm()
    response = llm.invoke([
        SystemMessage(content="You are the Red Team Auditor for the ANSE physics and mathematics simulator. You verify reasoning strictly."),
        HumanMessage(content=prompt)
    ])
    return response.content

def physics_bounds_thinker(state: ReviewState):
    """Deep Think Step 1: Physical constraints & hardware limits."""
    if state["domain"] == "pure_mathematics":
        state["thoughts"].append("Physics Check: Skipped for pure mathematics domain.")
        return state

    prompt = f"""Analyze the following solution for physical and hardware anomalies:
    Domain: {state['domain']}
    Problem: {state['problem_text']}
    Solution/Code: {state['solution_text']}
    
    Check constraints such as:
    1. Are the reported latencies impossible? (e.g. < 0.2ns for a single cycle on 5GHz).
    2. Are there impossible data structure claims? (e.g. O(1) sort).
    3. Are thermodynamic properties physically sound?
    
    Respond only with detected anomalies, or 'NONE' if none exist.
    """
    anomalies = call_llm(prompt)
    state["thoughts"].append("Physics Check: " + anomalies)
    return state

def epistemic_logic_thinker(state: ReviewState):
    """Deep Think Step 2: Formal logic & Epistemic Cheating (AST checks proxy)."""
    prompt = f"""Read this mathematical/logical solution:
    Problem: {state['problem_text']}
    Solution/Code: {state['solution_text']}
    
    Search for epistemic cheating:
    - Did the solver use `ring` or scalar algebra to bypass topological differential invariants?
    - Are there "junk theorems" or semantic erasure (reducing a complex space to 0 = 0)?
    - Are there hidden axioms introduced to force a proof without real construction?
    
    Respond only with detected epistemic logic failures, or 'NONE' if none exist.
    """
    anomalies = call_llm(prompt)
    state["thoughts"].append("Epistemic Check: " + anomalies)
    return state

def final_judgment(state: ReviewState):
    """Deep Think Step 3: Synthesis of hidden thoughts to verdict."""
    prompt = f"""Here are your previous internal thoughts on the solution:
    {state['thoughts']}
    
    Based *strictly* on these reflections, do you REJECT this solution due to physical impossibility or epistemic cheating, or ACCEPT it as sound?
    Respond explicitly with exactly one word: 'REJECT' or 'ACCEPT' on the first line. You may add justification below it.
    """
    verdict = call_llm(prompt)
    state["final_verdict"] = "REJECT" if "REJECT" in verdict[:20].upper() else "ACCEPT"
    return state

# Build the Graph
workflow = StateGraph(ReviewState)
workflow.add_node("physics", physics_bounds_thinker)
workflow.add_node("epistemics", epistemic_logic_thinker)
workflow.add_node("judge", final_judgment)

workflow.set_entry_point("physics")
workflow.add_edge("physics", "epistemics")
workflow.add_edge("epistemics", "judge")
workflow.add_edge("judge", END)

deep_think_validator_app = workflow.compile()

def audit_solution_with_deep_think(problem_text: str, solution_text: str, domain: str) -> bool:
    """
    Runs the full Deep Think MCTS PRM loop on a single solution.
    Returns True if ACCEPT, False if REJECT.
    """
    initial_state = {
        "problem_text": problem_text,
        "solution_text": solution_text,
        "domain": domain,
        "thoughts": [],
        "anomalies": [],
        "final_verdict": ""
    }
    
    result = deep_think_validator_app.invoke(initial_state)
    return result["final_verdict"] == "ACCEPT"

if __name__ == "__main__":
    # Smoke Test
    test_problem = "Calculate the trajectory of a photon in a black hole using general relativity."
    test_solution = "latency_ms = 0.0000001; O(1) array access. photon_path = [0, 1]"
    res = audit_solution_with_deep_think(test_problem, test_solution, "pure_physics")
    print("Final Verdict:", res)
