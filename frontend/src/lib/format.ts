/** Целое число для количеств ввода (убирает хвост .000000 из API) */
export function formatIntegerQty(val: string | number | null | undefined): string {
  if (val == null || val === '') return '0';
  const n = typeof val === 'string' ? parseFloat(val.replace(',', '.')) : val;
  if (isNaN(n)) return '0';
  return String(Math.round(n));
}

/** Format quantity: show as integer when whole, otherwise up to 2 decimals */
export function formatQty(val: string | number | null | undefined): string {
  if (val == null || val === '') return '—';
  const n = typeof val === 'string' ? parseFloat(val) : val;
  if (isNaN(n)) return String(val);
  if (Number.isInteger(n)) return String(n);
  const rounded = Math.round(n * 100) / 100;
  return rounded % 1 === 0 ? String(Math.round(rounded)) : rounded.toFixed(2);
}

/** Format amount: 50.000,00 (dot thousands, comma decimals, 2 decimals) */
export function formatAmount(val: string | number | null | undefined): string {
  if (val == null || val === '') return '—';
  const n = typeof val === 'string' ? parseFloat(val) : val;
  if (isNaN(n)) return String(val);
  const sign = n < 0 ? '-' : '';
  const absFixed = Math.abs(n).toFixed(2);
  const [intPart, decPart] = absFixed.split('.');
  const withDots = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `${sign}${withDots},${decPart}`;
}

/** Format date as DD.MM.YYYY */
export function formatDate(val: string | null | undefined): string {
  if (val == null || val === '') return '—';
  const d = new Date(val);
  if (isNaN(d.getTime())) return String(val);
  const day = String(d.getDate()).padStart(2, '0');
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const year = d.getFullYear();
  return `${day}.${month}.${year}`;
}
