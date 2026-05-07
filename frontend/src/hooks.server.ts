import type { Handle } from '@sveltejs/kit';

const backendOrigin = process.env.BACKEND_ORIGIN ?? 'http://backend:8000';

export const handle: Handle = async ({ event, resolve }) => {
  if (!event.url.pathname.startsWith('/api/')) {
    return resolve(event);
  }

  const target = new URL(event.url.pathname.replace(/^\/api/, '') || '/', backendOrigin);
  target.search = event.url.search;

  const headers = new Headers(event.request.headers);
  headers.delete('host');
  headers.delete('content-length');
  const body = ['GET', 'HEAD'].includes(event.request.method) ? undefined : event.request.body;

  return fetch(target, {
    method: event.request.method,
    headers,
    body,
    ...(body ? { duplex: 'half' } : {}),
    redirect: 'manual',
  } as RequestInit & { duplex: 'half' });
};
