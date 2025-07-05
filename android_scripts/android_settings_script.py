import subprocess
import time
import json
import re
from datetime import datetime
import uuid
import os
import sys
import signal

# --- Configuration ---
TEST_PACKAGE_NAME = 'com.example.settingsautomator.test'
PACKAGE_NAME = 'com.example.settingsautomator'
# This is the full component name from 'adb shell pm list instrumentation'
TEST_RUNNER_COMPONENT = f'{TEST_PACKAGE_NAME}/androidx.test.runner.AndroidJUnitRunner'
OUTPUT_JSON_FILE = 'result.json'
SCREENSHOT_PULL_DIR = './screenshots'
LOG_OUTPUT_FILE = 'debug_log.txt'

instrumentation_process = None


def run_command(command, shell=False):
    """Executes a shell command and returns its output and errors."""
    # Suppressed progress log: print(f"▶️  Executing: {' '.join(command) if not shell else command}")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        shell=shell,
        cwd='android_scripts'
    )
    if result.returncode != 0 and result.stderr:
        # Errors are printed to stderr
        print(f"❌ ERROR running command: {' '.join(command) if not shell else command}", file=sys.stderr)
        print(f"   Stderr: {result.stderr}", file=sys.stderr)
    return result.stdout.strip(), result.stderr.strip()

# --- MODIFICATION: Signal handler for graceful termination ---
def cleanup_and_exit(signum, frame):
    """Signal handler to stop the test and exit gracefully."""
    print("Termination signal received, attempting to stop the Android test...", file=sys.stderr)
    global instrumentation_process
    if instrumentation_process:
        # 1. Force-stop the test package on the Android device
        print(f"Stopping test package '{TEST_PACKAGE_NAME}' on device.", file=sys.stderr)
        run_command(['adb', 'shell', 'am', 'force-stop', TEST_PACKAGE_NAME])
        
        # 2. Terminate the host-side 'adb instrument' command
        print("Terminating host-side ADB process.", file=sys.stderr)
        instrumentation_process.terminate()
        
    sys.exit(1)


def get_environment_snapshot():
    """Gets device information using ADB."""
    # Suppressed progress log: print("\n--- Step 3a: Fetching environment snapshot ---")
    model, _ = run_command(['adb', 'shell', 'getprop', 'ro.product.model'])
    os_version, _ = run_command(['adb', 'shell', 'getprop', 'ro.build.version.release'])
    
    snapshot = {
        "device_type": model or "Unknown",
        "os": f"Android {os_version}" if os_version else "Unknown OS"
    }
    # Suppressed progress log: print(f"✅  Snapshot fetched: {snapshot}")
    return snapshot

def pull_screenshots_from_device():
    """Pulls screenshot files from the test app's private storage."""
    # Suppressed progress log: print("\n--- Step 3b: Pulling screenshots from device ---")
    
    if not os.path.exists(SCREENSHOT_PULL_DIR):
        os.makedirs(SCREENSHOT_PULL_DIR)
        
    run_command(['adb', 'pull', f'/sdcard/android/data/{PACKAGE_NAME}/files/.', SCREENSHOT_PULL_DIR])
    
    pulled_files = []
    if os.path.exists(SCREENSHOT_PULL_DIR):
        pulled_files = [os.path.join(SCREENSHOT_PULL_DIR, f) for f in os.listdir(SCREENSHOT_PULL_DIR) if f.endswith('.png')]
    
    return pulled_files


def generate_json_report(summary_output, verbose_output, env_snapshot, screenshot_files, runner_args, log_file_path):
    """
    Parses raw command output, generates a JSON report, writes it to a file, and returns the data.
    """
    report = {
        "job_id": runner_args.get("job_id", str(uuid.uuid4())),
        "status": "UNKNOWN",
        "project": runner_args.get("project"),
        "details": runner_args,
        "messages": ["Test suite initiated."],
        "logs": log_file_path,
        "started_at": None, "ended_at": None, "duration_seconds": 0,
        "passrate": "0.00%", "progress": "0/0",
        "videos": [],
        "screenshots": screenshot_files,
        "metadata": {
            "test_cases": [],
            "suite_execution_summary": { "total_tests": 0, "passed": 0, "failed": 0, "skipped": 0, "retest": 0, "failed_critical": 0 },
            "environment_snapshot": env_snapshot
        }
    }
    report["details"]["suite_name"] = runner_args.get("suite_name", "Unknown Test Suite")

    timestamps = re.findall(r"(\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d{3})", verbose_output)
    if timestamps:
        current_year = datetime.now().year
        start_time_dt = datetime.strptime(f"{current_year}-{timestamps[0]}", "%Y-%m-%d %H:%M:%S.%f")
        end_time_dt = datetime.strptime(f"{current_year}-{timestamps[-1]}", "%Y-%m-%d %H:%M:%S.%f")
        report["duration_seconds"] = round((end_time_dt - start_time_dt).total_seconds(), 3)

    test_cases = []
    test_map = {}  # To map test names to their index in the test_cases list
    
    # Pre-parse failure logs
    failure_pattern = re.compile(r"\d\) (TC\d{2}.*?)\(com\.example\.settingsautomator\.SettingsTestSuite\)\n(.*?)(?=\n\d\) |\nFAILURES!!!)", re.DOTALL)
    failed_tests = {name: error.strip() for name, error in failure_pattern.findall(summary_output)}

    # Regex to find test start/finish events and capture their timestamp and name
    log_pattern = re.compile(r"^(\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d{3}).*?I TestRunner: (started|finished): (.*?)\(com")
    current_year = datetime.now().year

    for line in verbose_output.splitlines():
        match = log_pattern.search(line)
        if match:
            timestamp_str, status, test_name = match.groups()
            timestamp_dt = datetime.strptime(f"{current_year}-{timestamp_str}", "%Y-%m-%d %H:%M:%S.%f")

            if status == 'started':
                # Determine status and logs using the pre-parsed failure data
                log_message = ""
                test_status = "PASSED"
                if test_name in failed_tests:
                    error_log = failed_tests[test_name]
                    test_status = "CRITICAL" if "java.lang.AssertionError" not in error_log else "FAILED"
                    log_message = error_log
                    report["messages"].append(f"Test '{test_name}' failed: {error_log.splitlines()[0]}")
                
                new_test = {
                    "id": test_name.split('_')[0],
                    "name": ' '.join(word.capitalize() for word in test_name.split('_')[1:]),
                    "status": test_status,
                    "logs": log_message,
                    "duration_ms": 0,
                    "_start_time": timestamp_dt  # Temporary field for calculation
                }
                test_cases.append(new_test)
                test_map[test_name] = len(test_cases) - 1
            
            elif status == 'finished':
                if test_name in test_map:
                    index = test_map[test_name]
                    start_time = test_cases[index].get("_start_time")
                    if start_time:
                        duration = int((timestamp_dt - start_time).total_seconds() * 1000)
                        test_cases[index]["duration_ms"] = round(duration, 3)
                        del test_cases[index]["_start_time"] # Clean up temporary field

    report["metadata"]["test_cases"].append({
        runner_args.get("suite_name", "SettingsTestSuite"): test_cases
    })

    summary_match = re.search(r"Tests run: (\d+),  Failures: (\d+)", summary_output)
    if summary_match:
        total_tests = int(summary_match.group(1))
        num_failures = int(summary_match.group(2))
        num_passed = total_tests - num_failures
        
        report["status"] = "FAILED" if num_failures > 0 else "PASSED"
        report["progress"] = f"{total_tests}/{total_tests}"
        
        if total_tests > 0:
            report["passrate"] = f"{(num_passed / total_tests) * 100:.2f}%"

        report["metadata"]["suite_execution_summary"].update({
            "total_tests": total_tests,
            "passed": num_passed,
            "failed": num_failures,
            "failed_critical": sum(1 for tc in test_cases if tc["status"] == "CRITICAL")
        })
    
    report["messages"].append("Test suite finished.")
    
    with open(OUTPUT_JSON_FILE, 'w') as f:
        json.dump(report, f, indent=4)
    
    return report


def main():
    """Main function to run the test suite and process results."""
    signal.signal(signal.SIGTERM, cleanup_and_exit)
    
    if len(sys.argv) < 2:
        # Usage errors are printed to stderr
        print("❌ USAGE ERROR: Please provide the runner details as a JSON string argument.", file=sys.stderr)
        print("   Example: python3 android_runner.py '{\"suite_name\": \"MySmokeTest\"}'", file=sys.stderr)
        sys.exit(1)
        
    json_argument_string = " ".join(sys.argv[1:])
        
    try:
        runner_args = json.loads(json_argument_string)
    except json.JSONDecodeError:
        # Usage errors are printed to stderr
        print("❌ USAGE ERROR: The provided argument is not a valid JSON string.", file=sys.stderr)
        print(f"Attempted to parse: {json_argument_string}", file=sys.stderr)
        sys.exit(1)

    run_command(['adb', 'logcat', '-c'])
    
    # --- MODIFICATION: Use subprocess.Popen to run the test ---
    global instrumentation_process
    command = ['adb', 'shell', 'am', 'instrument', '-w', TEST_RUNNER_COMPONENT]
    instrumentation_process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd='android_scripts'
    )
    # Wait for the process to complete and get the output
    summary_output, summary_error = instrumentation_process.communicate()
    # Clear the global variable once the process is done
    instrumentation_process = None
    
    if "FAILURES!!!" not in summary_output and "OK" not in summary_output:
        # Execution errors are printed to stderr
        print("Encountered a critical error during test execution. Aborting.", file=sys.stderr)
        print(f"Output: {summary_output}\nError: {summary_error}", file=sys.stderr)
        return

    time.sleep(2) 

    env_snapshot = get_environment_snapshot()
    screenshot_files = pull_screenshots_from_device()
    
    verbose_output, _ = run_command(['adb', 'logcat', '-d', '-s', 'TestRunner'])

    with open(LOG_OUTPUT_FILE, 'w') as f:
        f.write("--- Summary Report (from am instrument) ---\n" + summary_output + "\n\n")
        f.write("--- Verbose Log (from logcat) ---\n" + verbose_output)

    # Generate the report and get the data back
    report_data = generate_json_report(summary_output, verbose_output, env_snapshot, screenshot_files, runner_args, LOG_OUTPUT_FILE)
    
    # Print the final JSON report to stdout
    print(json.dumps(report_data, indent=4))

if __name__ == "__main__":
    main()