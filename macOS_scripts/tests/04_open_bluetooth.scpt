log "TEST 4: Opening Bluetooth Settings..."
tell application "System Settings"
    open location "x-apple.systempreferences:Bluetooth"
    activate
end tell
delay 1
return "Bluetooth settings opened."