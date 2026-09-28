/**
 * Права текущего пользователя на фронте: меню, кнопки, защита маршрутов.
 *
 * Это только удобство интерфейса — источник истины бэкенд (каждый запрос проверяется там).
 */
import { derived, writable } from 'svelte/store';
import type { CurrentUser, PermissionLevel, SectionKey } from '$lib/api';

export const LEVEL_ORDER: PermissionLevel[] = ['none', 'view', 'edit', 'full'];

/** Разделы в порядке меню. Совпадает с app/permissions.py SECTIONS. */
export const SECTION_ROUTES: { key: SectionKey; path: string; label: string }[] = [
  { key: 'monthly_plans', path: '/monthly-plans', label: 'Месячные планы' },
  { key: 'parts', path: '/parts', label: 'Детали' },
  { key: 'devices', path: '/devices', label: 'Приборы' },
  { key: 'bom', path: '/bom', label: 'Спецификации' },
  { key: 'import', path: '/import', label: 'Загрузка спецификаций' },
  { key: 'orders', path: '/orders', label: 'Заказы клиентов' },
  { key: 'invoices', path: '/invoices', label: 'Счета от поставщиков' },
  { key: 'statistics', path: '/statistics', label: 'Статистика' },
];

export const currentUser = writable<CurrentUser | null>(null);

export function levelOf(user: CurrentUser | null, section: SectionKey): PermissionLevel {
  if (!user) return 'none';
  if (user.is_superuser) return 'full';
  return user.permissions?.[section] ?? 'none';
}

export function hasLevel(user: CurrentUser | null, section: SectionKey, level: PermissionLevel): boolean {
  return LEVEL_ORDER.indexOf(levelOf(user, section)) >= LEVEL_ORDER.indexOf(level);
}

/**
 * `$can('parts', 'edit')` в разметке. edit — создавать и править, full — ещё и удалять/архивировать.
 */
export const can = derived(
  currentUser,
  ($user) => (section: SectionKey, level: PermissionLevel = 'view') => hasLevel($user, section, level),
);

/** Какой раздел (или админка) отвечает за путь страницы. null — страница без ограничений. */
export function routeRequirement(pathname: string): { section: SectionKey } | { admin: true } | null {
  if (pathname === '/admin' || pathname.startsWith('/admin/')) return { admin: true };
  const hit = SECTION_ROUTES.find((r) => pathname === r.path || pathname.startsWith(r.path + '/'));
  return hit ? { section: hit.key } : null;
}

export function canOpenPath(user: CurrentUser | null, pathname: string): boolean {
  const req = routeRequirement(pathname);
  if (!req) return true;
  if ('admin' in req) return !!user?.is_superuser;
  return hasLevel(user, req.section, 'view');
}

/** Первая доступная страница — стартовая после входа. */
export function firstAllowedPath(user: CurrentUser | null): string | null {
  const hit = SECTION_ROUTES.find((r) => hasLevel(user, r.key, 'view'));
  if (hit) return hit.path;
  return user?.is_superuser ? '/admin' : null;
}
