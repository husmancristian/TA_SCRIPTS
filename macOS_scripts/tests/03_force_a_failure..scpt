log "TEST 3: Attempting an action that will fail..."
tell application "System Events"
    tell process "System Settings"
        -- This button does not exist, so this will cause an error.
        click ui element "Non-Existent Button" of window 1
    end tell
end tell