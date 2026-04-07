import { test, expect } from '@playwright/test'

test.describe('App initialization', () => {
  test('shows navbar with title and Day 1', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('GoKart Factory')).toBeVisible()
    await expect(page.getByText('Day 1')).toBeVisible()
  })

  test('stores JWT in localStorage after init', async ({ page }) => {
    await page.goto('/')
    // Wait for the app to finish initializing (tabs become visible)
    await expect(page.getByRole('button', { name: 'Work Orders' })).toBeVisible()

    const token = await page.evaluate(() => localStorage.getItem('gokart_token'))
    expect(token).toBeTruthy()
  })

  test('all five tabs are visible', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('button', { name: 'Work Orders' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Work Centers' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'All Operations' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Factory Timeline' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Work Order Timeline' })).toBeVisible()
  })

  test('simulation controls are always visible', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('button', { name: '+1 Day' })).toBeVisible()
    await expect(page.getByRole('button', { name: '+5 Days' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Next Event' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Start Over' })).toBeVisible()
  })

  test('Work Orders tab is active by default', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('Create New Work Order')).toBeVisible()
  })
})
