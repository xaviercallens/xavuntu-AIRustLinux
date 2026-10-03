import sys
import json
sys.path.append('deploy/scripts')
import run_gke_tests

project = 'gen-lang-client-0625573011'
run_gke_tests.install_chaos_mesh()
run_gke_tests.build_and_push_images(project)
run_gke_tests.deploy_benchmark_pods(project)

baseline = run_gke_tests.run_baseline_tests()
stress = run_gke_tests.run_stress_tests()
chaos = run_gke_tests.run_chaos_tests(project)

report = run_gke_tests.generate_comparison_report(baseline, stress, chaos)
print("FINAL_REPORT_JSON_START")
print(json.dumps(report, indent=2))
print("FINAL_REPORT_JSON_END")
