package com.example.settingsautomator


import android.content.Context
import android.content.Intent
import android.os.Environment
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.rule.GrantPermissionRule
import androidx.test.uiautomator.*
import org.junit.Assert.*
import org.junit.Before
import org.junit.FixMethodOrder
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.MethodSorters
import java.io.File

/**
 * Naming convention (test01_, test02_) is used with @FixMethodOrder to run tests sequentially.
 */
@RunWith(AndroidJUnit4::class)
@FixMethodOrder(MethodSorters.NAME_ASCENDING)
class SettingsTestSuite {


    private lateinit var device: UiDevice
    private val settingsPackage = "com.android.settings"
    private val launchTimeout = 5000L

    @Before
    fun startFromHomeScreen() {
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

    // --- PASSING TESTS (6) ---

    private fun takeScreenshot(testName: String) {
        // Save to the app's private files directory, which requires no permissions.
        val context = ApplicationProvider.getApplicationContext<Context>()
        val screenshotDir = context.getExternalFilesDir(null)
        val screenshotFile = File(screenshotDir, "${testName}.png")
        device.takeScreenshot(screenshotFile)
        assertTrue("Screenshot was not created at ${screenshotFile.absolutePath}", screenshotFile.exists())
    }

    @Test
    fun TC01_openNetworkAndInternet() {
        val networkSetting = device.findObject(By.text("Connections"))
        networkSetting.click()
        val wifiLabel = device.wait(Until.findObject(By.text("Wi-Fi")), launchTimeout)
        takeScreenshot( "TC01_network_settings")
        assertNotNull("Wi-Fi label not found on the next screen.", wifiLabel)
    }

    @Test
    fun TC02_openQuickShare() {
        device.findObject(By.text("Connected devices")).click()
        val connectionPrefs = device.wait(Until.findObject(By.text("Quick Share")), launchTimeout)
        assertNotNull("'Quick Share' not found.", connectionPrefs)
    }

    @Test
    fun TC03_openNotes() {
        device.findObject(By.text("Galaxy AI")).click()
        val defaultApps = device.wait(Until.findObject(By.textContains("Note assist")), launchTimeout)
        assertNotNull("'Note assist' not found.", defaultApps)
    }

    @Test
    fun TC04_openModes() {
        device.findObject(By.text("Modes and Routines")).click()
        val brightness = device.wait(Until.findObject(By.text("Sleep")), launchTimeout)
        assertNotNull("'Brightness level' not found.", brightness)
    }

    @Test
    fun TC05_openSoundSettings() {
        // Use a scroll to find an item that might be off-screen
        val list = UiScrollable(UiSelector().scrollable(true))
        val soundAndVibration =  device.wait(Until.findObject(By.textContains("Sounds and vibration")), launchTimeout)
        soundAndVibration.click()
        val volume = device.wait(Until.findObject(By.textContains("volume")), launchTimeout)
        assertNotNull("Volume controls not found.", volume)
    }

    @Test
    fun TC06_verifySearchIconExists() {
        // This test just checks for the presence of the search icon
        val searchIcon = device.findObject(By.desc("Search settings")) // content-description
        takeScreenshot( "TC06_network_settings")
        assertTrue("Search icon should exist and be enabled.", searchIcon.isEnabled)
    }


    // --- FAILING TESTS (3) ---

    @Test
    fun TC07_findNonExistentSetting() {
        // This test will fail because "Teleportation" setting does not exist.
        // findObject will return null, and the assertion will fail.
        val nonExistentSetting = device.findObject(By.text("Teleportation"))
        assertNotNull("The 'Teleportation' setting should not be null.", nonExistentSetting)
    }

    @Test
    fun TC08_incorrectTextAssertion() {
        // This test fails because the text on the button is not what we assert it to be.
        device.findObject(By.text("Display")).click()
        val brightness = device.wait(Until.findObject(By.text("Brightness level")), launchTimeout)
        assertEquals("Text does not match", "Maximum Brightness", brightness.text)
    }

    @Test
    fun TC09_assertingElementIsHidden() {
        // This test fails because we assert that the "Connections" text is NOT visible, when it is.
        val displaySetting = device.findObject(By.text("Connections"))
        takeScreenshot("TC09_network_settings")
        // We expect it to be null/not found, but it will be found, causing failure.
        assertNull("The 'Display' setting should be hidden, but it was found.", displaySetting)
    }


    // --- CRITICALLY FAILING TEST (1) ---

    @Test
    fun TC10_forceNullPointerException() {
        // This test represents a CRITICAL failure.
        // It tries to perform an action on an object that doesn't exist (is null),
        // which will throw a NullPointerException and crash this specific test.
        val nonExistentObject: UiObject2? = device.findObject(By.text("Flux Capacitor"))
        // The line below will crash because nonExistentObject is null.
        nonExistentObject!!.click()
    }
}