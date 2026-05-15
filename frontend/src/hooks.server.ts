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

  const method = event.request.method;
  if (method === 'GET' || method === 'HEAD') {
    return fetch(target, {
      method,
      headers,
      redirect: 'manual',
    });
  }

  // Проксирование multipart через undici + ReadableStream + duplex часто даёт TypeError: fetch failed.
  // Буферизуем тело — для загрузки вложений к счетам размер приемлемый.
  const raw = await event.request.arrayBuffer();
  const body = raw.byteLength > 0 ? raw : undefined;

  return fetch(target, {
    method,
    headers,
    body,
    redirect: 'manual',
  });
};
