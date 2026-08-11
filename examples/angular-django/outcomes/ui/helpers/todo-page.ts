import { Locator, Page, expect } from '@playwright/test';

/**
 * This project's todo page, as the promises about it reach it: opening the
 * list, putting something on it, finding a row again, reading the count back.
 *
 * Every one of those is an implementation choice the prompts deliberately
 * don't make -- that the list is this page, that a row is `li.item`, that the
 * count is the line under the heading. Written once here, the specs beside
 * them are left saying what each promise actually claims, and a change to the
 * markup is one file rather than one per outcome.
 *
 * What deliberately isn't here: the assertion a promise turns on. A code owner
 * approves a translation by reading it against its prompt, and a claim moved
 * behind a helper is one they'd have to go looking for. These wait for the
 * page to be in the state they say they leave it in, and stop there.
 */

/** The list, loaded and finished loading. */
export const openTodoList = async (page: Page): Promise<void> => {
  await page.goto('/');
  // The count reads 'Loading…' until the list has arrived, so waiting for it
  // is waiting for a page that can be acted on rather than one that has been
  // served.
  await expect(page.locator('.subtitle')).toContainText('left');
};

/** The row for an item, whether or not it's there yet. */
export const itemRow = (page: Page, title: string): Locator =>
  page.locator('li.item', { hasText: title });

/** An item's title as the list shows it -- what to count when asking whether
 * an item is on the list at all. */
export const itemTitle = (page: Page, title: string): Locator =>
  page.locator('li.item span.title', { hasText: title });

/** Adds an item and returns its row, once the list is showing it. */
export const addItem = async (page: Page, title: string): Promise<Locator> => {
  await page.fill('input[name="title"]', title);
  await page.click('button.add-btn');
  await expect(itemTitle(page, title)).toBeVisible();
  return itemRow(page, title);
};

/** How many items the page says are left, read off the page rather than
 * worked out from what a test did. */
export const remaining = async (page: Page): Promise<number> => {
  const shown = await page.locator('.subtitle').textContent();
  const [, left] = shown!.match(/^\s*(\d+) of \d+ left\s*$/)!;
  return Number(left);
};
