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
