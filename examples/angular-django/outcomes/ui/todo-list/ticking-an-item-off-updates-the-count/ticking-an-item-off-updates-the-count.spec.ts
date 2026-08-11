import { expect, test } from '@playwright/test';

import { addItem, openTodoList, remaining } from '../../helpers/todo-page';

/**
 * Translated from prompt.md, beside this file: "ticking an item off updates
 * how many are left".
 *
 * The implementation choices the prompt deliberately doesn't make are made in
 * ../../helpers/todo-page.ts, which every promise about this list shares: the
 * count is the line this project's todo page puts under its heading ("2 of 5
 * left"). The one this test makes for itself is that an item is ticked with the
 * checkbox its row carries.
 *
 * What the prompt is about is that the two agree, so the count is read back
 * from the page after every change rather than worked out from what this test
 * did. And it ticks an item *back* on as well as off, because the prompt says
 * that's the point: a count that only ever counts down looks correct through
 * the obvious test.
 *
 * The prompt says nothing about how done items are shown -- struck through,
 * greyed out, moved -- so neither does this.
 */
test('the count of what is left follows the list, in both directions', async ({ page }) => {
  const title = 'sharpen the good knife';

  await openTodoList(page);
  const row = await addItem(page, title);

  const before = await remaining(page);

  await row.getByRole('checkbox').check();
  await expect(row).toHaveClass(/done/);
  expect(await remaining(page)).toBe(before - 1);

  await row.getByRole('checkbox').uncheck();
  await expect(row).not.toHaveClass(/done/);
  expect(await remaining(page)).toBe(before);
});
