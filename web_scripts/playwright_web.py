import sys
import json
import subprocess
import re
import uuid
import os
from datetime import datetime, timezone

def clean_ansi_escape_codes(text):
    """
    Removes ANSI escape codes (used for color in terminals) from a string.
    Playwright's error messages are full of them.
    """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def transform_playwright_result(playwright_json_str, details):

    try:
        playwright_data = json.loads(playwright_json_str)
    except json.JSONDecodeError as e:
        print(f"Error decoding Playwright JSON output: {e}", file=sys.stderr)
        print(f"Received data: {playwright_json_str}", file=sys.stderr)
        return None

    run_start_time = datetime.fromisoformat(playwright_data['stats']['startTime'].replace('Z', '+00:00'))
    run_duration = playwright_data['stats']['duration'] / 1000.0
    run_end_time = datetime.fromtimestamp(run_start_time.timestamp() + run_duration, tz=timezone.utc)

    final_result = {
        "job_id": "",
        "status": "PASSED" if playwright_data['stats']['unexpected'] == 0 else "FAILED",
        "project": details.get("platform", "Unknown"),
        "details": details,
        "messages": ["Test suite initiated."],
        "logs": "playwright_output.log",
        "started_at": run_start_time.isoformat().replace('+00:00', 'Z'),
        "ended_at": run_end_time.isoformat().replace('+00:00', 'Z'),
        "duration_seconds": round(run_duration, 3),
        "passrate": "0.00%",
        "progress": f"{playwright_data['stats']['expected'] + playwright_data['stats']['unexpected']}/{playwright_data['stats']['expected'] + playwright_data['stats']['unexpected']}",
        "videos": [],
        "screenshots": [],
        "metadata": {
            "test_cases": [],
            "suite_execution_summary": {
                "total_tests": playwright_data['stats']['expected'] + playwright_data['stats']['unexpected'],
                "passed": playwright_data['stats']['expected'],
                "failed": playwright_data['stats']['unexpected'],
                "skipped": playwright_data['stats']['skipped'],
                "retest": 0,
                "failed_critical": playwright_data['stats']['unexpected']
            },
            "environment_snapshot": {
                "device_type": "Desktop",
                "os": sys.platform
            }
        }
    }

    test_cases_list = []
    for suite in playwright_data.get('suites', []):
        def find_specs(current_suite):
            specs = []
            for spec in current_suite.get('specs', []):
                specs.append(spec)
            for sub_suite in current_suite.get('suites', []):
                specs.extend(find_specs(sub_suite))
            return specs
        all_specs = find_specs(suite)
        for i, spec in enumerate(all_specs):
            test_case = {
                "id": f"TC{i+1:02d}",
                "name": spec['title'].replace('.', '_').replace(' ', ''),
                "status": "PASSED" if spec['ok'] else "FAILED",
                "logs": ""
            }
            if not spec['ok']:
                error_details = spec['tests'][0]['results'][0].get('error', {})
                error_message = clean_ansi_escape_codes(error_details.get('message', 'No error message found.'))
                error_stack = clean_ansi_escape_codes(error_details.get('stack', 'No stack trace found.'))
                test_case['logs'] = f"{error_message.strip()}\n{error_stack.strip()}"
                final_result["messages"].append(f"Test '{spec['title']}' failed: {error_message.splitlines()[0]}")
            test_cases_list.append(test_case)

    final_result["metadata"]["test_cases"].append({details.get("suite_name", "UnknownSuite"): test_cases_list})

    if final_result['metadata']['suite_execution_summary']['total_tests'] > 0:
        pass_rate_val = (final_result['metadata']['suite_execution_summary']['passed'] / final_result['metadata']['suite_execution_summary']['total_tests']) * 100
        final_result['passrate'] = f"{pass_rate_val:.2f}%"

    final_result["messages"].append("Test suite finished.")
    return final_result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 playwright_web.py '<json_arguments>'", file=sys.stderr)
        sys.exit(1)
    try:
        job_details = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        print("Error: Invalid JSON provided as argument.", file=sys.stderr)
        sys.exit(1)
        
    web_scripts_dir = 'web_scripts'
    command = "npx playwright test chrome-settings.spec.ts --reporter=json"
    
    process = subprocess.run(
        command, 
        shell=True, 
        capture_output=True, 
        text=True, 
        cwd=web_scripts_dir
    )

    # ===================================================================
    #  Write stdout and stderr to playwright_output.log
    # ===================================================================
    log_filename = "playwright_output.log"
    print(f"Writing Playwright output to {log_filename}...", file=sys.stderr)
    try:
        with open(log_filename, 'w', encoding='utf-8') as log_file:
            log_file.write("--- Playwright stdout ---\n")
            log_file.write(process.stdout)
            log_file.write("\n\n--- Playwright stderr ---\n")
            log_file.write(process.stderr)
    except IOError as e:
        print(f"Error writing to log file: {e}", file=sys.stderr)
    # ===================================================================


    if process.returncode != 0 and not process.stdout:
        sys.exit(1)

    final_json_result = transform_playwright_result(process.stdout, job_details)

    if final_json_result:
        screenshots_dir_path = os.path.join(web_scripts_dir, 'screenshots_web')
        
        screenshot_paths = []
        if os.path.isdir(screenshots_dir_path):
            for filename in os.listdir(screenshots_dir_path):
                if filename.lower().endswith('.png'):
                    path = os.path.join(screenshots_dir_path, filename).replace('\\', '/')
                    screenshot_paths.append(path)
        
        final_json_result['screenshots'] = screenshot_paths

    if final_json_result:
        print(json.dumps(final_json_result, indent=4))