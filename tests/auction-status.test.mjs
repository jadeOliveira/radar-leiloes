import { test } from 'node:test';
import assert from 'node:assert/strict';
import { displayStatus } from '../src/auctionStatus.ts';
const today = '2026-11-28';
const listing = (status, dates) => ({ status, auction_events: dates.map(date => ({ date })) });
test('expired official listings from the reported cards are excluded from active', () => {
  for (const day of ['2026-10-21', '2026-11-03']) {
    assert.equal(displayStatus(listing('active', [day]), today), 'ended_unverified');
  }
});
test('a remaining auction stage and auctions today remain eligible', () => {
  assert.equal(displayStatus(listing('active', ['2026-10-21', today]), today), 'active');
  assert.equal(displayStatus(listing('active', ['2026-12-01']), today), 'active');
});
test('explicit outcomes remain authoritative', () => {
  for (const status of ['closed', 'sold', 'cancelled', 'suspended']) {
    assert.equal(displayStatus(listing(status, ['2026-10-21']), today), status);
  }
});
test('unknown dates and missing dates do not invent an outcome', () => {
  assert.equal(displayStatus(listing('active', []), today), 'active');
  assert.equal(displayStatus(listing('unknown', []), today), 'unknown');
  assert.equal(displayStatus(listing('unknown', [today]), today), 'scheduled_unverified');
  assert.equal(displayStatus(listing('scheduled_unverified', ['2026-11-27']), today), 'ended_unverified');
});

test('seven-day window includes today and day seven across month boundaries', async () => {
  const { isWithinNextSevenDays } = await import('../src/auctionStatus.ts');
  for (const day of ['2026-11-28', '2026-12-01', '2026-12-05']) {
    assert.equal(isWithinNextSevenDays(listing('scheduled_unverified', [day]), today), true);
  }
  for (const dates of [[], ['2026-11-27'], ['2026-12-06']]) {
    assert.equal(isWithinNextSevenDays(listing('active', dates), today), false);
  }
  assert.equal(isWithinNextSevenDays(listing('unknown', ['2026-11-01', '2026-12-02']), today), true);
  for (const status of ['closed', 'cancelled', 'sold', 'suspended']) {
    assert.equal(isWithinNextSevenDays(listing(status, ['2026-12-01']), today), false);
  }
  assert.equal(isWithinNextSevenDays(listing('active', ['2027-01-03']), '2026-12-28'), true);
});
