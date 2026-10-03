#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anse.core.lean_agent_loop import LeanAgentLoop
from anse.config import get_config
from anse.core.api_extractor import APIExtractor
from anse.memory.chroma_rag import ChromaRAG

def main():
    get_config()
    rag = ChromaRAG()
    extractor = APIExtractor()
    loop = LeanAgentLoop(extractor=extractor, rag=rag)
    
    # Try a simple theorem first
    theorem_name = "test_theorem"
    statement = "(a b : Nat) : a + b = b + a"
    
    print(f"Starting auto-improvement loop for {theorem_name}")
    res = loop.run(theorem_name, statement, max_retries=3)
    
    print("Result:")
    print(f"Converged: {res['converged']}")
    print(f"Energy: {res['energy']}")
    print(f"Iterations: {res['iterations']}")
    print("Code:")
    print(res["code"])

if __name__ == "__main__":
    main()
