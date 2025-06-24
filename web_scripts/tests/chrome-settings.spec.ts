import { test, expect, chromium, BrowserContext, Page } from '@playwright/test';
import { tmpdir } from 'os';
import { join } from 'path';

test.describe('Simplified Chrome Settings Tests (3rd Revision)', () => {
  let context: BrowserContext;
  let page: Page;

  // This setup part is necessary to access chrome:// pages and should remain.
  test.beforeAll(async () => {
    const userDataDir = join(tmpdir(), `playwright_chrome_user_data_${Date.now()}`);
    context = await chromium.launchPersistentContext(userDataDir, {
      headless: false,
    });
  });

  test.afterAll(async () => {
    await context.close();
  });

  test.beforeEach(async () => {
    page = await context.newPage();
  });

  test.afterEach(async () => {
    await page.close();
  });

  // TEST 1: This test should now PASS.
  // Using getByRole for a more stable locator.
  test('TC01. [PASS] Navigate to Appearance and see the Theme section', async () => {
    await page.goto('chrome://settings/appearance');
    // FIX: Using getByRole is more robust. It finds the link element with the name "Theme".
    await expect(page.getByRole('link', { name: 'Theme' })).toBeVisible();
  });

  // TEST 2: This test is INTENDED to FAIL.
  // This test works correctly by failing on the title assertion.
  test('TC02. [FAIL] Navigate to Accessibility and check for wrong title', async () => {
    await page.goto('chrome://settings/accessibility');
    await expect(page).toHaveTitle('This is a Wrong Title');
  });

  // TEST 3: This test should now PASS.
  // Using getByRole for a more stable locator.
  test('TC03. [PASS] Navigate to Autofill and see Password Manager link', async () => {
    await page.goto('chrome://settings/autofill');
    // FIX: Using getByRole to find the link named "Password Manager".
    await expect(page.getByRole('link', { name: 'Password Manager' })).toBeVisible();
  });

  // TEST 4: This test is INTENDED to FAIL.
  // This test works correctly by looking for an element that doesn't exist.
  test('TC04. [FAIL] Navigate to Downloads and find a non-existent element', async () => {
    await page.goto('chrome://settings/downloads');
    await expect(page.locator('#aButtonThatDoesNotExist')).toBeVisible();
  });

  // TEST 5: This test should now PASS.
  // Using a more precise text locator.
  test('TC05. [PASS] Navigate to Privacy and check the main header', async () => {
    await page.goto('chrome://settings/privacy');
    // FIX: Targeting the h1 element specifically by its exact text content.
    await page.screenshot({ path: 'screenshots_web/TC05_privacy.png', fullPage: false });
    await expect(page.getByRole('heading', { name: 'Privacy and security', exact: true })).toBeVisible();
  });

  // TEST 6: This test should now PASS.
  // The 'Performance' page is now sometimes called 'Power'. Using a new locator.
  test('TC06. [PASS] Navigate to Performance and see Memory Saver toggle', async () => {
    // Some Chrome versions rename this page to 'Power'. We'll stick with 'performance'.
    await page.goto('chrome://settings/performance');
    // FIX: Targeting the specific settings-toggle-button that has a sub-label of "Memory Saver".
    await expect(page.locator('settings-toggle-button', { hasText: 'Memory Saver' })).toBeVisible();
  });

  // TEST 7: This test is INTENDED to FAIL.
  // Locator fixed, but assertion is still incorrect on purpose.
  test('TC07. [FAIL] Navigate to Languages and check for incorrect header text', async () => {
    await page.goto('chrome://settings/languages');
    // FIX: Using getByRole to correctly find the header. The assertion will now correctly fail.
    const languagesHeader = page.getByRole('heading', { name: 'Preferred languages' });
    await page.screenshot({ path: 'screenshots_web/TC07_languages.png', fullPage: false });

    await expect(languagesHeader).toHaveText('This is Not the Right Header');
  });

  // TEST 8: This test should now PASS.
  // Using getByRole for a more stable locator.
  test('TC08. [PASS] Navigate to Reset and see the reset profile row', async () => {
    await page.goto('chrome://settings/reset');
    // FIX: Finding the link by its accessible name.
    await expect(page.getByRole('link', { name: 'Restore settings to their original defaults' })).toBeVisible();
  });

  // TEST 9: This test is INTENDED to FAIL.
  // Locator fixed, but assertion is still incorrect on purpose.
  test('TC09. [FAIL] Navigate to Cookies and expect "Block all cookies" to be selected', async () => {
    await page.goto('chrome://settings/cookies');
    await page.screenshot({ path: 'screenshots_web/TC09_cookies.png', fullPage: false });
    await page.screenshot({ path: 'screenshots_web/TC09_cookies-full.png', fullPage: true });
    // FIX: Using getByRole to find the radio button by its name.
    // This will now correctly find the button, and the toBeChecked() will fail as intended.
    await expect(page.getByRole('radio', { name: 'Block all cookies' })).toBeChecked();
  });

  // TEST 10: This test should PASS.
  // This test worked previously and the locator is still valid.
  test('TC010. [PASS] Navigate to About page', async () => {
    await page.goto('chrome://settings/help');
    await page.screenshot({ path: 'screenshots_web/TC10_help.png', fullPage: false });

    await expect(page.locator('settings-about-page')).toBeVisible();
  });
});