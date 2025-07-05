import sys
import json
import subprocess
import re
import uuid
import os
from datetime import datetime, timezone
import signal

playwright_process = None

def cleanup_and_exit(signum, frame):
    """Signal handler to stop Playwright and all its child processes."""
    print("Termination signal received, stopping Playwright...", file=sys.stderr)
    global playwright_process
    if playwright_process and playwright_process.poll() is None:
        try:
            # On Unix-like systems, kill the entire process group.
            if os.name != 'nt':
                print(f"Killing process group with PGID: {playwright_process.pid}", file=sys.stderr)
                os.killpg(os.getpgid(playwright_process.pid), signal.SIGTERM)
            else: # Fallback for Windows
                playwright_process.terminate()
        except ProcessLookupError:
            # Process may have already finished between the check and the kill command
            print("Process already terminated.", file=sys.stderr)
            pass
    sys.exit(1)

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
        "project": "webApp",
        "details": details,
        "messages": ["Test suite initiated."],
        "logs": "playwright_output.txt",
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
    # --- MODIFICATION: Register the signal handler ---
    signal.signal(signal.SIGTERM, cleanup_and_exit)
    
    if len(sys.argv) < 2:
        print("Usage: python3 playwright_web.py '<json_arguments>'", file=sys.stderr)
        sys.exit(1)
        
    json_argument_string = " ".join(sys.argv[1:])
    
    try:
        job_details = json.loads(json_argument_string)
    except json.JSONDecodeError as e:
        print("Error: Invalid JSON provided as argument.", file=sys.stderr)
        print(f"Attempted to parse: {json_argument_string}", file=sys.stderr)
        sys.exit(1)
    

    web_scripts_dir = 'web_scripts'
    containerized = os.getenv('CONTAINER')
    if(containerized == 'true' ):
        # print(f"Running 'npm install' inside '{web_scripts_dir}'...", file=sys.stderr)
        npm_command = "npm install"
        
        install_process = subprocess.run(
            npm_command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=web_scripts_dir # Run this command in the web_scripts directory
        )

        # Check if npm install was successful before proceeding
        if install_process.returncode != 0:
            print("Error: 'npm install' failed.", file=sys.stderr)
            print("--- npm install stderr ---", file=sys.stderr)
            print(install_process.stderr, file=sys.stderr)
            sys.exit(1) # Exit immediately if dependencies can't be installed
            
        # print("'npm install' completed successfully.", file=sys.stderr)
    
        command = "xvfb-run --auto-servernum npx playwright test chrome-settings.spec.ts --reporter=json"
    else:
        command = "npx playwright test chrome-settings.spec.ts --reporter=json"

    # On Unix, preexec_fn=os.setsid creates a new process group.
    # This allows us to kill the parent and all its children (browsers) at once.
    preexec_fn = os.setsid if os.name != 'nt' else None
    
    playwright_process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=web_scripts_dir,
        preexec_fn=preexec_fn
    )
    
    # Wait for completion and capture output
    stdout_data, stderr_data = playwright_process.communicate()
    return_code = playwright_process.returncode
    playwright_process = None # Clear global variable

    # ===================================================================
    #  Write stdout and stderr to playwright_output.log
    # ===================================================================
    log_filename = "playwright_output.txt"
    # print(f"Writing Playwright output to {log_filename}...", file=sys.stderr)
    try:
        with open(log_filename, 'w', encoding='utf-8') as log_file:
            log_file.write("--- Playwright stdout ---\n")
            log_file.write(stdout_data)
            log_file.write("\n\n--- Playwright stderr ---\n")
            log_file.write(stderr_data)
    except IOError as e:
        print(f"Error writing to log file: {e}", file=sys.stderr)
    # ===================================================================

    # Exit if the command failed and produced no parsable output
    if return_code != 0 and not stdout_data:
        sys.exit(1)

    final_json_result = transform_playwright_result(stdout_data, job_details)

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