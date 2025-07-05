import sys
import json
import subprocess
import re
import uuid
import os
from datetime import datetime, timezone
import signal

playwright_process = None
termination_signal_received = False

def graceful_shutdown_handler(signum, frame):
    """Signal handler to gracefully stop Playwright and let the main script handle the output."""
    global playwright_process, termination_signal_received
    
    # Set the flag so the main loop knows why the process is ending
    if not termination_signal_received:
        print("Termination signal received, attempting graceful shutdown of Playwright...", file=sys.stderr)
        termination_signal_received = True

    if playwright_process and playwright_process.poll() is None:
        try:
            # Send SIGTERM to the entire process group. This is what Ctrl+C does and
            # allows Playwright to generate its final report.
            if os.name != 'nt':
                os.killpg(os.getpgid(playwright_process.pid), signal.SIGINT)
            else: # Fallback for Windows
                playwright_process.terminate()
        except ProcessLookupError:
            print("Process already terminated.", file=sys.stderr)
            pass


def clean_ansi_escape_codes(text):
    """
    Removes ANSI escape codes (used for color in terminals) from a string.
    Playwright's error messages are full of them.
    """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def transform_playwright_result(playwright_json_str, details):
    """
    Transforms the raw Playwright JSON output into the final, structured test result.
    """
    try:
        playwright_data = json.loads(playwright_json_str)
    except json.JSONDecodeError as e:
        print(f"Error decoding Playwright JSON output: {e}", file=sys.stderr)
        print(f"Received data: {playwright_json_str}", file=sys.stderr)
        return None

    def get_test_status(spec):
        """
        Determines the correct test status by inspecting the detailed results,
        not just the 'ok' boolean.
        """
        # Guard against malformed spec objects
        if not spec.get('tests'):
            return 'SKIPPED'

        test_run = spec['tests'][0]
        
        # A test is purely 'skipped' if it has no results and its status is 'skipped'.
        if test_run.get('status') == 'skipped' and not test_run.get('results'):
            return 'SKIPPED'
            
        # If there are results, that's the most reliable source of truth.
        if test_run.get('results'):
            run_result = test_run['results'][0]
            pw_status = run_result.get('status')  # e.g., 'passed', 'failed', 'timedOut', 'interrupted'

            if pw_status == 'passed':
                return 'PASSED'
            # Treat 'interrupted' as 'SKIPPED' in the final report.
            elif pw_status == 'interrupted':
                return 'SKIPPED'
            # Any other non-passed status is a failure.
            else:
                return 'FAILED'
        
        # Fallback for any other case
        return 'FAILED'

    run_start_time = datetime.fromisoformat(playwright_data['stats']['startTime'].replace('Z', '+00:00'))
    run_duration = playwright_data['stats']['duration'] / 1000.0
    run_end_time = datetime.fromtimestamp(run_start_time.timestamp() + run_duration, tz=timezone.utc)

    # The stats object from Playwright gives the correct top-level counts
    stats = playwright_data.get('stats', {})
    total_run = stats.get('expected', 0) + stats.get('unexpected', 0) + stats.get('flaky', 0)
    passed_count = stats.get('expected', 0)
    failed_count = stats.get('unexpected', 0) + stats.get('flaky', 0)
    skipped_count = stats.get('skipped', 0)
    
    # Determine overall status from stats
    overall_status = "PASSED"
    if failed_count > 0:
        overall_status = "FAILED"
    elif total_run == 0 and skipped_count > 0:
        overall_status = "SKIPPED"
    
    final_result = {
        "job_id": "",
        "status": overall_status, # Use status derived from stats
        "project": "webApp",
        "details": details,
        "messages": ["Test suite initiated."],
        "logs": "playwright_output.txt",
        "started_at": run_start_time.isoformat().replace('+00:00', 'Z'),
        "ended_at": run_end_time.isoformat().replace('+00:00', 'Z'),
        "duration_seconds": round(run_duration, 3),
        "passrate": "0.00%",
        "progress": f"{total_run}/{total_run + skipped_count}",
        "videos": [],
        "screenshots": [],
        "metadata": {
            "test_cases": [],
            "suite_execution_summary": {
                "total_tests": total_run + skipped_count,
                "passed": passed_count,
                "failed": failed_count,
                "skipped": skipped_count,
                "retest": 0,
                "failed_critical": failed_count
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
            test_status = get_test_status(spec)
            test_case = {
                "id": f"TC{i+1:02d}",
                "name": spec['title'].replace('.', '_').replace(' ', ''),
                "status": test_status,
                "logs": ""
            }
            # Only look for error logs if the test actually failed.
            if test_status == 'FAILED' and spec['tests'][0].get('results'):
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
    # Register the  non-exiting signal handler ---
    signal.signal(signal.SIGTERM, graceful_shutdown_handler)
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
 
    npm_command = "npm install"
    install_process = subprocess.run(
        npm_command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=web_scripts_dir
    )

    if install_process.returncode != 0:
        print("Error: 'npm install' failed.", file=sys.stderr)
        print("--- npm install stderr ---", file=sys.stderr)
        print(install_process.stderr, file=sys.stderr)
        sys.exit(1)
        
    containerized = os.getenv('CONTAINER')
    if(containerized == 'true' ):
        command = "xvfb-run --auto-servernum npx playwright test chrome-settings.spec.ts --reporter=json"
    else:
        command = "npx playwright test chrome-settings.spec.ts --reporter=json"

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
    
    stdout_data, stderr_data = playwright_process.communicate()
    return_code = playwright_process.returncode
    playwright_process = None

    log_filename = "playwright_output.txt"
    try:
        with open(log_filename, 'w', encoding='utf-8') as log_file:
            log_file.write("--- Playwright stdout ---\n")
            log_file.write(stdout_data)
            log_file.write("\n\n--- Playwright stderr ---\n")
            log_file.write(stderr_data)
    except IOError as e:
        print(f"Error writing to log file: {e}", file=sys.stderr)

    # The main logic for handling results after termination ---
    # We attempt to parse the output even if the return code is non-zero,
    # as an aborted run is expected to have a non-zero exit code.
    if not stdout_data:
        if termination_signal_received:
            print("Error: Playwright was aborted but produced no output.", file=sys.stderr)
        else:
            print("Error: Playwright command failed and produced no output.", file=sys.stderr)
        sys.exit(1)

    final_json_result = transform_playwright_result(stdout_data, job_details)

    if final_json_result:
        # If the run was aborted, override the status and add a message.
        if termination_signal_received:
            final_json_result['status'] = 'ABORTED'
            final_json_result['messages'].append("Test run was aborted by a termination signal.")

        screenshots_dir_path = os.path.join(web_scripts_dir, 'screenshots_web')
        screenshot_paths = []
        if os.path.isdir(screenshots_dir_path):
            for filename in os.listdir(screenshots_dir_path):
                if filename.lower().endswith('.png'):
                    path = os.path.join(screenshots_dir_path, filename).replace('\\', '/')
                    screenshot_paths.append(path)
        final_json_result['screenshots'] = screenshot_paths
        
        if os.path.exists(log_filename):
            # Ensure the 'logs' field contains the correct relative path.
            final_json_result['logs'] = log_filename
            print(f"Log file '{log_filename}' found and added to report.", file=sys.stderr)
        else:
            # If the log file wasn't created for some reason, clear the field.
            final_json_result['logs'] = ""
            print(f"Warning: Log file '{log_filename}' not found.", file=sys.stderr)



        print(json.dumps(final_json_result, indent=4))
    else:
        # This will be reached if transform_playwright_result returned None
        print("Error: Could not parse Playwright's JSON output.", file=sys.stderr)
        sys.exit(1)