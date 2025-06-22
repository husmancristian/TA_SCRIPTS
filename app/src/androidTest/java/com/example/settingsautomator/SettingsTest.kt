package com.example.settingsautomator

import android.content.Context
import android.content.Intent
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Assert.assertNotNull
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SettingsTest {

    private lateinit var device: UiDevice
    private val settingsPackage = "com.android.settings"
    private val launchTimeout = 5000L

    @Before
    fun startMainActivityFromHomeScreen() {
        // Initialize UiDevice instance
        device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())

        // Start from the home screen
        device.pressHome()

        // Wait for launcher
        val launcherPackage = device.launcherPackageName
        assertNotNull(launcherPackage)
        device.wait(Until.hasObject(By.pkg(launcherPackage).depth(0)), launchTimeout)

        // Launch the settings app
        val context = ApplicationProvider.getApplicationContext<Context>()
        val intent = context.packageManager.getLaunchIntentForPackage(settingsPackage)
        intent?.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK) // Clear out any previous instances
        context.startActivity(intent)

        // Wait for the app to appear
        device.wait(Until.hasObject(By.pkg(settingsPackage).depth(0)), launchTimeout)
    }

    @Test
    fun testOpenNetworkSettings() {
        // Find the "Network & internet" setting by its text.
        // This text might be different on other devices/Android versions.
        // Use "uiautomatorviewer" to find the correct text or resource-id.
        val networkAndInternet = device.findObject(By.text("Network & internet"))

        // Click on the setting
        networkAndInternet.click()

        // Optional: Wait for the next screen to appear and verify something
        // For example, wait for the "Wi-Fi" text to be visible on the new screen
        val wifiSetting = device.wait(Until.findObject(By.text("Wi-Fi")), launchTimeout)
        assertNotNull("Wi-Fi option not found on the next screen", wifiSetting)
    }
}