type DatedAuction = { status?: string; auction_events?: Array<{ date?: string | null }> };

export function displayStatus(property: DatedAuction, today: string): string {
  const status = property.status ?? 'unknown';
  if (['closed', 'cancelled', 'sold', 'suspended'].includes(status)) return status;
  const dates = (property.auction_events ?? [])
    .map((event) => event.date)
    .filter((value): value is string => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value));
  if (dates.length && dates.every((day) => day < today)) return 'ended_unverified';
  if (status === 'unknown' && dates.some((day) => day >= today)) return 'scheduled_unverified';
  return status;
}

export function isWithinNextSevenDays(property: DatedAuction, today: string): boolean {
  if (['closed', 'cancelled', 'sold', 'suspended'].includes(property.status ?? '')) return false;
  const end = new Date(`${today}T12:00:00Z`);
  end.setUTCDate(end.getUTCDate() + 7);
  const lastDay = end.toISOString().slice(0, 10);
  return (property.auction_events ?? []).some(({ date }) =>
    typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date) && date >= today && date <= lastDay,
  );
}
