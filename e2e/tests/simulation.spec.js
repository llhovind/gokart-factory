import { test, expect } from '@playwright/test'

/** Read the current day number from the navbar pill */
async function getCurrentDay(page) {
  const text = await page.locator('nav span.bg-blue-800').textContent()
  const match = text.match(/Day (\d+)/)
  return match ? parseInt(match[1], 10) : null
}

test.describe('Simulation controls', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('button', { name: '+1 Day' })).toBeVisible()
  })

  test('+1 Day advances the day by 1', async ({ page }) => {
    const before = await getCurrentDay(page)
    await page.getByRole('button', { name: '+1 Day' }).click()
    await expect(page.getByText('Advancing…')).toBeHidden({ timeout: 15_000 })
    const after = await getCurrentDay(page)
    expect(after).toBe(before + 1)
  })

  test('+5 Days advances the day by 5', async ({ page }) => {
    const before = await getCurrentDay(page)
    await page.getByRole('button', { name: '+5 Days' }).click()
    await expect(page.getByText('Advancing…')).toBeHidden({ timeout: 15_000 })
    const after = await getCurrentDay(page)
    expect(after).toBe(before + 5)
  })

  test('Next Event advances the day by at least 1', async ({ page }) => {
    // Create a work order first so there is an event to advance to
    await expect(page.locator('select').first()).not.toBeDisabled()
    await page.getByRole('button', { name: 'Create Work Order' }).click()
    await expect(page.getByText(/Work Order #\d+/)).toBeVisible({ timeout: 10_000 })

    const before = await getCurrentDay(page)
    await page.getByRole('button', { name: 'Next Event' }).click()
    await expect(page.getByText('Advancing…')).toBeHidden({ timeout: 15_000 })
    const after = await getCurrentDay(page)
    expect(after).toBeGreaterThan(before)
  })

  test('buttons are disabled while advancing', async ({ page }) => {
    await page.getByRole('button', { name: '+1 Day' }).click()
    // The "Advancing…" text appears while loading
    await expect(page.getByText('Advancing…')).toBeVisible()
    await expect(page.getByRole('button', { name: '+1 Day' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '+5 Days' })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Next Event' })).toBeDisabled()
    // Wait for completion
    await expect(page.getByText('Advancing…')).toBeHidden({ timeout: 15_000 })
  })

  test('Start Over resets day to 1 and clears work orders', async ({ page }) => {
    // Create a WO and advance a day so there's something to clear
    await expect(page.locator('select').first()).not.toBeDisabled()
    await page.getByRole('button', { name: 'Create Work Order' }).click()
    await expect(page.getByText(/Work Order #\d+/)).toBeVisible({ timeout: 10_000 })

    await page.getByRole('button', { name: '+1 Day' }).click()
    await expect(page.getByText('Advancing…')).toBeHidden({ timeout: 15_000 })

    await page.getByRole('button', { name: 'Start Over' }).click()
    await expect(page.getByText('Advancing…')).toBeHidden({ timeout: 15_000 })

    // Day resets to 1
    await expect(page.getByText('Day 1')).toBeVisible()

    // Work orders table is empty
    await expect(page.getByText('No open work orders.')).toBeVisible()
  })
})
