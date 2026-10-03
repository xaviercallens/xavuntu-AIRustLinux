import os
import sys
import json
import logging

try:
    from pymilvus import MilvusClient
    from sentence_transformers import SentenceTransformer
except ImportError:
    logging.warning("Missing RAG dependencies. Run: uv pip install pymilvus sentence-transformers")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LeanInteractiveAgent")

MILVUS_DB_PATH = "./mathlib4_rag.db"
COLLECTION_NAME = "mathlib4_lemmas"

class MathlibRAG:
    def __init__(self):
        try:
            self.client = MilvusClient(MILVUS_DB_PATH)
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            self.enabled = True
        except Exception as e:
            logger.warning(f"RAG disabled (Milvus not found or model not loaded): {e}")
            self.enabled = False

    def query_lemmas(self, goal: str, top_k: int = 3) -> list[str]:
        if not self.enabled:
            return ["Real.sqrt_le_iff", "geom_mean_le_arith_mean"] # Fallback mocks
            
        try:
            vector = self.model.encode([goal])[0].tolist()
            res = self.client.search(
                collection_name=COLLECTION_NAME,
                data=[vector],
                limit=top_k,
                output_fields=["lemma_name", "signature"]
            )
            
            retrieved = []
            for hits in res:
                for hit in hits:
                    entity = hit['entity']
                    retrieved.append(f"{entity['lemma_name']}: {entity['signature']}")
            return retrieved
        except Exception as e:
            logger.error(f"Milvus query failed: {e}")
            return []

def call_local_prover_llm(prompt: str) -> str:
    """Mock integration for DeepSeek-Prover-V1.5"""
    return "sorry"

def feed_error_to_mcts(tactic: str, error_msg: str):
    logger.info(f"[MCTS UPDATE] Tactic '{tactic}' failed with: {error_msg}")

def interactive_lean_agent(theorem_statement: str, rag_engine: MathlibRAG) -> str:
    """Agentic loop proving a theorem step-by-step using REPL and Milvus RAG."""
    logger.info(f"Initializing Interactive Theorem Prover for: {theorem_statement}")
    
    class MockLeanState:
        def is_solved(self): return False
        def get_goals(self): return ["⊢ ∀ (a b : ℝ), 0 ≤ a → 0 ≤ b → 2 * math.sqrt (a * b) ≤ a + b"]
        def run_tactic(self, tactic):
            class MockResult:
                def is_error(self): return True
                @property
                def error_message(self): return "unknown identifier 'math.sqrt'"
                @property
                def new_state(self): return self
            return MockResult()
            
    lean_state = MockLeanState()
    proof_script = []
    max_steps = 10
    step = 0
    
    while not lean_state.is_solved() and step < max_steps:
        current_goal = lean_state.get_goals()[0]
        logger.info(f"Current Goal: {current_goal}")
        
        # Semantic Search (Milvus RAG)
        useful_lemmas = rag_engine.query_lemmas(current_goal)
        logger.info(f"RAG Retrieved Lemmas:\n" + "\n".join(useful_lemmas))
        
        # Prompt Specialized Model
        prompt = f"""
        You are a Lean 4 expert.
        Current Goal: {current_goal}
        Potentially useful Mathlib lemmas: {useful_lemmas}
        Output ONLY the next valid Lean 4 tactic.
        """
        proposed_tactic = call_local_prover_llm(prompt)
        logger.info(f"Proposed Tactic: {proposed_tactic}")
        
        result = lean_state.run_tactic(proposed_tactic)
        
        if result.is_error():
            logger.warning(f"Lean Error: {result.error_message}. Agent will rethink.")
            feed_error_to_mcts(proposed_tactic, result.error_message)
            break
        else:
            proof_script.append(proposed_tactic)
            lean_state = result.new_state
            
        step += 1
        
    return "\n".join(proof_script)

if __name__ == "__main__":
    logger.info("Starting Phase 4: Interactive Formal Mathematician (Milvus RAG Edition)")
    rag = MathlibRAG()
    interactive_lean_agent("theorem am_gm : ...", rag)
