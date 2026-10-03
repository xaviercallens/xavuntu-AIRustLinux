"""
Self-Healing Loop Pattern with Gemini Ultra and Antigravity Guard.

Connects LLM code generation directly to deterministic verification (AST validation,
phantom import auditing, Ruff linting, MyPy type checks) in an automated closed-loop.
"""

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_and_heal(
    prompt: str,
    target_file: str,
    max_iterations: int = 3,
    model_name: str = "gemini-2.5-ultra",
    api_key: str | None = None,
) -> str:
    """
    Generate code with Gemini Ultra and iteratively repair it using deterministic guard tracebacks.

    Parameters:
        prompt: Initial engineering instruction or task specification.
        target_file: Path to write the candidate Python code.
        max_iterations: Number of self-repair cycles before raising RuntimeError.
        model_name: Gemini model ID (e.g. 'gemini-2.5-ultra' or 'gemini-1.5-pro').
        api_key: Optional Gemini API key (defaults to GEMINI_API_KEY environment variable).

    Returns:
        The verified, fully compliant Python code.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError as err:
        raise ImportError(
            "google-genai package is required for the Ultra self-healing loop. "
            "Install it via `pip install google-genai`."
        ) from err

    client = genai.Client(api_key=api_key) if api_key else genai.Client()
    current_prompt = prompt
    target_path = Path(target_file).resolve()
    guard_script = Path(__file__).parent.parent.parent / "antigravity_guard.py"
    python_exe = sys.executable

    for iteration in range(max_iterations):
        logger.info(
            "Self-healing iteration %d/%d for %s", iteration + 1, max_iterations, target_path.name
        )
        response = client.models.generate_content(
            model=model_name,
            contents=current_prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                system_instruction=(
                    "Generate production-grade Python code adhering to strict typing (PEP 484) "
                    "and clean formatting. Output only clean, executable Python code inside a single ```python block."
                ),
            ),
        )

        raw_text = response.text or ""
        code = raw_text.replace("```python", "").replace("```", "").strip()

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Run deterministic guard
        result = subprocess.run(
            [python_exe, str(guard_script), str(target_path)],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            logger.info("Code verified cleanly on iteration %d.", iteration + 1)
            return code

        # Feed the deterministic traceback back into Ultra for self-correction
        logger.warning(
            "Verification failed on iteration %d. Extracting pain signal...", iteration + 1
        )
        current_prompt = (
            f"Original Goal: {prompt}\n\n"
            f"The generated code failed verification with the following errors:\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}\n\n"
            f"Fix all issues, eliminate phantom/unresolved imports, satisfy MyPy/Ruff, and return the corrected code."
        )

    raise RuntimeError(
        f"Agent failed to satisfy deterministic quality gates for {target_file} within {max_iterations} iterations."
    )
