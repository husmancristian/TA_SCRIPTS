-- Opens the Wi-Fi settings pane directly.
log "TEST 1: Opening Wi-Fi Settings..."
tell application "System Settings"
    open location "x-apple.systempreferences:Wi-Fi"
    activate
end tell
-- A delay to ensure the UI is ready for the next test
delay 1
return "Wi-Fi settings opened."