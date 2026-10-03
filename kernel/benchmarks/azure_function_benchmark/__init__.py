"""
Azure Function: C to Rust Compilation Benchmark
HTTP trigger to run compilation quality benchmarks
"""

import azure.functions as func
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from c_to_rust_compilation_benchmark import CToRustBenchmark


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Azure Function entry point for compilation benchmark

    Query parameters:
    - modules: Comma-separated list of module names (optional, defaults to all)
    - workspace: Path to workspace (optional, uses default)
    - format: 'json' or 'markdown' (default: json)
    """
    logging.info('C to Rust compilation benchmark triggered')

    try:
        # Parse parameters
        modules_param = req.params.get('modules')
        workspace = req.params.get('workspace', '/workspace')
        output_format = req.params.get('format', 'json')

        # Parse module list
        modules = None
        if modules_param:
            modules = [m.strip() for m in modules_param.split(',')]

        # Run benchmark
        logging.info(f"Running benchmark on workspace: {workspace}")
        benchmark = CToRustBenchmark(workspace)
        comparisons, metrics = benchmark.run_benchmark(modules)

        # Format response
        if output_format == 'markdown':
            report = benchmark.generate_report(comparisons, metrics)
            return func.HttpResponse(
                report,
                mimetype="text/markdown",
                status_code=200
            )
        else:
            # JSON response
            response_data = {
                "status": "success",
                "metrics": metrics.to_dict(),
                "comparisons": comparisons,
                "summary": {
                    "translation_accuracy": f"{metrics.translation_accuracy:.1f}%",
                    "rust_success": f"{metrics.rust_success_count}/{metrics.total_modules}",
                    "error_reduction": f"{metrics.error_reduction:.1f}%",
                    "performance_ratio": f"{metrics.performance_ratio:.2f}x",
                    "benchmark_passed": (
                        metrics.translation_accuracy >= 75 and
                        metrics.error_reduction >= 50
                    )
                }
            }

            return func.HttpResponse(
                json.dumps(response_data, indent=2),
                mimetype="application/json",
                status_code=200
            )

    except Exception as e:
        logging.error(f"Benchmark failed: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": str(e)
            }),
            mimetype="application/json",
            status_code=500
        )
