import { expect, test } from '@playwright/test';

import { addItem, itemRow, itemTitle, openTodoList } from '../../helpers/todo-page';

/**
 * Translated from prompt.md, beside this file: "deleting an item takes it off
 * the list for good".
 *
 * The implementation choices the prompt deliberately doesn't make are made in
 * ../../helpers/todo-page.ts, which every promise about this list shares: the
 * list is this project's own todo page, and a row is found by the text it
 * carries. The two this test makes for itself are that an item is deleted with
 * the × its row carries, and that loading the application again is
 * `page.reload()`.
 *
 * The prompt's third clause -- "deleting one item leaves every other item
 * alone" -- is checked against another item this test adds itself rather than
 * against the whole list. That's a real narrowing and a deliberate one: what
 * else is on the list is whatever the run before left, and asserting on it
 * would make this promise fail for something that isn't about deleting. What
 * it still catches is the failure the clause is about -- a delete that takes
 * more than it was asked for.
 */
test('a deleted item is gone, stays gone, and takes nothing else with it', async ({ page }) => {
  const kept = 'water the ficus';
  const deleted = 'return the library book';

  await openTodoList(page);
  const keptRow = await addItem(page, kept);
  await addItem(page, deleted);

  // The one that stays is ticked off first, so what's checked afterwards is
  // that it kept its done-state and not only its text.
  await keptRow.getByRole('checkbox').check();
  await expect(keptRow).toHaveClass(/done/);

  await page.getByRole('button', { name: `Delete ${deleted}` }).click();

  // Gone straight away.
  await expect(itemTitle(page, deleted)).toHaveCount(0);

  // And still gone when the application is loaded again -- the half of the
  // promise worth having, since something that only disappears from the screen
  // reads as working right up until somebody reloads.
  await page.reload();
  await expect(itemTitle(page, deleted)).toHaveCount(0);

  // And the item beside it is exactly as it was.
  await expect(itemRow(page, kept)).toHaveClass(/done/);
});
