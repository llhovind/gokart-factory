import { test, expect } from '@playwright/test'

test.describe('Work Orders', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // Wait for app init and inventory to load (dropdowns become enabled)
    await expect(page.getByRole('button', { name: 'Create Work Order' })).toBeVisible()
    await expect(page.locator('select').first()).not.toBeDisabled()
  })

  test('inventory dropdowns are populated', async ({ page }) => {
    const selects = page.locator('select')
    const count = await selects.count()
    expect(count).toBe(4)

    // Each dropdown should have at least one option
    for (let i = 0; i < count; i++) {
      const optionCount = await selects.nth(i).locator('option').count()
      expect(optionCount).toBeGreaterThan(0)
    }
  })

  test('creates a work order and shows success message', async ({ page }) => {
    // Dropdowns auto-select the first item via watchEffect, so just submit
    await page.getByRole('button', { name: 'Create Work Order' }).click()

    // Success banner should appear with a WO number
    await expect(page.getByText(/Work Order #\d+/)).toBeVisible({ timeout: 10_000 })
  })

  test('new work order appears in the Open Work Orders table', async ({ page }) => {
    await page.getByRole('button', { name: 'Create Work Order' }).click()
    await expect(page.getByText(/Work Order #\d+/)).toBeVisible({ timeout: 10_000 })

    // The WO table should now have at least one row with a WO- prefix
    await expect(page.getByText(/WO-\d+/).first()).toBeVisible()
  })

  test('work order row shows a current stage badge', async ({ page }) => {
    await page.getByRole('button', { name: 'Create Work Order' }).click()
    await expect(page.getByText(/Work Order #\d+/)).toBeVisible({ timeout: 10_000 })
    // Wait for the full submit cycle (fetchAllOps is called after success message appears)
    await expect(page.getByRole('button', { name: 'Create Work Order' })).toBeEnabled()

    // Stage badge exists and is non-empty (exact op name depends on inventory state)
    const stageBadge = page.locator('tbody tr').first().locator('td').last().locator('span')
    await expect(stageBadge).toBeVisible()
    await expect(stageBadge).not.toBeEmpty()
  })

  test('"No open work orders" shown when none exist', async ({ page }) => {
    // Fresh tenant — table is empty before creating anything
    await expect(page.getByText('No open work orders.')).toBeVisible()
  })
})
