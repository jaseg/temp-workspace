// @watch start
// templates/repo/diff/**
// web_src/js/webcomponents/lazy-webc.js
// web_src/js/vendor/kicad-diff/**
// @watch end

// Visual KiCad diff (kicaddiff build tag).

import {expect} from '@playwright/test';
import {test} from './utils_e2e.ts';

test('KiCad files are shown with the visual diff', async ({page}) => {
  const response = await page.goto('/user2/kicad-diff-test/commits/branch/main', {waitUntil: 'domcontentloaded'});
  expect(response?.status()).toBe(200);
  // The newest commit changes the schematic.
  await page.locator('table a[href*="/kicad-diff-test/commit/"]').first().click();

  const viewer = page.locator('kicad-diff');
  await expect(viewer).toHaveAttribute('old-src', /\/user2\/kicad-diff-test\/media\/commit\/[0-9a-f]+\/resistors\.kicad_sch$/);
  await expect(viewer).toHaveAttribute('new-src', /\/media\/commit\/[0-9a-f]+\/resistors\.kicad_sch$/);
  // The viewer loads both versions and lists the changes.
  await expect(viewer.locator('.change')).toHaveCount(5);
  await expect(viewer.locator('.change').first()).toContainText('2 pins disconnected');

  // The source view is one click away.
  await page.locator('.file-view-toggle').first().click();
  await expect(page.locator('.diff-file-body .code-diff').first()).toBeVisible();
});
