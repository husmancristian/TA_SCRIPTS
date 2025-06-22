-- A simple check to ensure we are on the right screen.
log "TEST 2: Checking for Wi-Fi details..."
tell application "System Events"
    tell process "System Settings"
        -- We just check if a static text element "Wi-Fi" exists in the window.
        if not (static text "Wi-Fi" of window 1 exists) then
            error "Could not verify that the Wi-Fi screen is open."
        end if
    end tell
end tell
return "Wi-Fi screen verified."