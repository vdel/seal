import { expect, test } from '@playwright/test';

import { addItem, itemTitle, openTodoList } from '../../helpers/todo-page';

/**
 * Translated from prompt.md, beside this file: "an item I add is still on the
 * list after a reload".
 *
 * The implementation choices the prompt deliberately doesn't make are made in
 * ../../helpers/todo-page.ts, which every promise about this list shares: the
 * list is this project's own todo page, and an item is added through the field
 * above it. A reload is `page.reload()` -- the application loaded again against
 * the same running environment, with nothing restarted and nothing re-seeded,
 * exactly as the prompt says.
 *
 * The prompt says nothing about *where* on the list a new item appears, so
 * neither does this: what's checked is that it's on the list, with the text it
 * was given.
 */
test('an item added before a reload is still on the list after it', async ({ page }) => {
  const title = 'buy a stroopwafel';

  await openTodoList(page);
  await addItem(page, title);

  await page.reload();

  await expect(itemTitle(page, title)).toBeVisible();
});
