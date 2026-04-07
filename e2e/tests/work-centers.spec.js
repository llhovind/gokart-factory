import { test, expect } from '@playwright/test'

/** Helper: create a WO, advance days until at least one op is awaiting_completion */
async function setupWithAwaitingOp(page) {
  await page.goto('/')
  await expect(page.locator('select').first()).not.toBeDisabled()

  // Create a work order
  await page.getByRole('button', { name: 'Create Work Order' }).click()
  await expect(page.getByText(/Work Order #\d+/)).toBeVisible({ timeout: 10_000 })

  // Advance time until an awaiting_completion operation exists (max 10 days)
  for (let i = 0; i < 10; i++) {
    await page.getByRole('button', { name: 'Next Event' }).click()
    // Wait for loading to clear
    await expect(page.getByText('Advancing…')).toBeHidden({ timeout: 15_000 })

    // Check if any work center badge (orange pill) is showing
    const badge = page.locator('.bg-orange-400').first()
    if (await badge.isVisible()) break
  }
}

test.describe('Work Centers', () => {
  test('shows all 8 work center tabs', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Work Centers' }).click()

    const expected = ['Purchasing', 'Receiving', 'Inventory', 'Incoming QC', 'Assembly', 'Finishing', 'Inspection', 'Shipping']
    for (const wc of expected) {
      await expect(page.getByRole('button', { name: new RegExp(wc) })).toBeVisible()
    }
  })

  test('Purchasing is selected by default', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Work Centers' }).click()
    // The active tab has blue-600 class; Purchasing button should be styled as active
    const purchasingBtn = page.getByRole('button', { name: /Purchasing/ })
    await expect(purchasingBtn).toHaveClass(/bg-blue-600/)
  })

  test('empty state shown for work center with no operations', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Work Centers' }).click()
    // Fresh tenant — Purchasing has no operations yet
    await expect(page.getByText(/No operations in Purchasing/)).toBeVisible()
  })

  test('Complete button appears and completes an operation', async ({ page }) => {
    await setupWithAwaitingOp(page)

    await page.getByRole('button', { name: 'Work Centers' }).click()

    // Find the work center tab that has a badge (awaiting_completion ops)
    const wcButtons = page.locator('.flex.flex-wrap.gap-2 button')
    const count = await wcButtons.count()

    let clicked = false
    for (let i = 0; i < count; i++) {
      const btn = wcButtons.nth(i)
      const badge = btn.locator('.bg-orange-400')
      if (await badge.isVisible()) {
        await btn.click()
        clicked = true
        break
      }
    }
    expect(clicked).toBe(true)

    // Complete button should now be visible in the table
    const completeBtn = page.getByRole('button', { name: 'Complete' }).first()
    await expect(completeBtn).toBeVisible()

    await completeBtn.click()

    // Button should briefly show "…" then disappear or refresh
    // After refresh, the operation should no longer show "Complete"
    await expect(completeBtn).toBeHidden({ timeout: 10_000 })
  })

  test('switching work center tabs loads different operations', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Work Centers' }).click()

    // Click Receiving — different empty-state message
    await page.getByRole('button', { name: /Receiving/ }).click()
    await expect(page.getByText(/No operations in Receiving/)).toBeVisible()

    // Purchasing button is no longer active
    const purchasingBtn = page.getByRole('button', { name: /Purchasing/ })
    await expect(purchasingBtn).not.toHaveClass(/bg-blue-600/)
  })
})
