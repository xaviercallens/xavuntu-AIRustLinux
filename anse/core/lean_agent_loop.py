from __future__ import annotations
import logging
import time
import re
from typing import Any

from anse.core.api_extractor import APIExtractor
from anse.formal.lean_runner import LeanKernelVerifier
from anse.memory.chroma_rag import ChromaRAG
from anse.config import get_config

logger = logging.getLogger("LeanAgentLoop")

SYSTEM_PROMPT = """You are an expert formal mathematician using Lean 4.
Write a valid Lean 4 proof for the given theorem.
Do NOT use `sorry` or `admit`. Ensure all hypotheses are properly imported from Mathlib.
Return ONLY valid Lean 4 code enclosed in ```lean ... ``` blocks.
"""

RETRY_PROMPT = """The previous Lean 4 proof failed to compile.
Here is the compilation error from `lake build` or `lake env lean`:
{error}

Please fix the proof. Make sure you have the right Mathlib imports and the proof is complete.
Return ONLY valid Lean 4 code enclosed in ```lean ... ``` blocks.
"""

class LeanAgentLoop:
    def __init__(self, extractor: APIExtractor | None = None, rag: ChromaRAG | None = None):
        self.extractor = extractor or APIExtractor()
        self.rag = rag or ChromaRAG()
        self.verifier = LeanKernelVerifier()

    def run(self, theorem_name: str, formal_statement: str, max_retries: int = 5) -> dict[str, Any]:
        """
        Runs the closed-loop agent to synthesize and compile a Lean 4 proof.
        """
        logger.info(f"Starting LeanAgentLoop for theorem: {theorem_name}")
        
        # 1. Query RAG for Similar Templates
        context_docs = self.rag.query_literature(formal_statement, n_results=2)
        code_templates = self.rag.query_code(formal_statement, n_results=2)
        
        rag_context = ""
        if context_docs or code_templates:
            rag_context = "Relevant Context from Memory:\n"
            for doc in context_docs:
                rag_context += doc.get("document", "") + "\n\n"
            for tpl in code_templates:
                rag_context += tpl.get("document", "") + "\n\n"

        prompt = f"{rag_context}\nTASK: Prove the following theorem in Lean 4.\nTheorem Name: {theorem_name}\nStatement: {formal_statement}"
        
        start_time = time.time()
        best_code = ""
        last_error = ""
        
        for iteration in range(1, max_retries + 1):
            logger.info(f"Iteration {iteration}/{max_retries}")
            
            # Extract LLM response
            raw_response, _ = self.extractor.extract(prompt=prompt, system_prompt=SYSTEM_PROMPT)
            
            # Extract lean code
            code = self._extract_code(raw_response)
            if not code:
                code = raw_response # Fallback
                
            # Save to temporary lean file in formal/ANSE/
            test_file = self.verifier.formal_dir / "ANSE" / f"{theorem_name}_temp.lean"
            try:
                # Add basic imports if not present
                if "import Mathlib" not in code:
                    code = "import Mathlib\n\n" + code
                
                test_file.write_text(code, encoding="utf-8")
                
                # Check via LeanRunner
                res = self.verifier.verify_theorem_axioms("ANSE." + f"{theorem_name}_temp", theorem_name)
                
                if res.compiled_successfully and not res.has_sorry:
                    logger.info(f"Success! Theorem {theorem_name} verified.")
                    
                    # --- DEEP THINK RED TEAM AUDIT ---
                    from anse.core.red_team import DeepThinkAuditor
                    auditor = DeepThinkAuditor(self.extractor)
                    audit_state = auditor.invoke({
                        "math_problem": formal_statement,
                        "lean_code": code,
                        "python_metrics": {"error": 0.0, "latency_ms": res.elapsed_ms},
                        "thoughts": []
                    })
                    
                    if "REJECT" in audit_state["verdict"]:
                        logger.warning(f"Red Team Audit Rejected: {audit_state['verdict']}")
                        # Treat as a failure, loop back with the Red Team's thoughts as pain signal
                        last_error = "Red Team Rejected your solution due to epistemic flaws:\n" + "\n".join(audit_state["thoughts"])
                        prompt += "\n\n" + RETRY_PROMPT.format(error=last_error)
                        continue
                        
                    logger.info("Red Team Audit Passed. Attestation Verified.")
                    # ---------------------------------
                    
                    # Index successful solution to RAG
                    self.rag.index_code_solution(
                        doc_id=f"lean_{theorem_name}_{int(time.time())}",
                        code_content=code,
                        task_prompt=formal_statement,
                        language="lean4",
                        energy=res.energy_score
                    )
                    return {
                        "converged": True,
                        "iterations": iteration,
                        "energy": res.energy_score,
                        "code": code,
                        "duration_ms": (time.time() - start_time) * 1000.0
                    }
                else:
                    last_error = res.output
                    prompt += "\n\n" + RETRY_PROMPT.format(error=last_error)
            finally:
                if test_file.exists():
                    test_file.unlink()

        return {
            "converged": False,
            "iterations": max_retries,
            "energy": 1000000.0,
            "code": code,
            "error": last_error,
            "duration_ms": (time.time() - start_time) * 1000.0
        }

    def _extract_code(self, text: str) -> str:
        pattern = r"```(?:lean|lean4)?\s*\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
