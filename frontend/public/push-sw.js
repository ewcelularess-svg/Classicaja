self.addEventListener('push', event => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = {}; }
  const title = data.title || 'ClassificaJá';
  const options = {
    body: data.body || 'Há uma novidade no ClassificaJá.',
    icon: data.icon || '/logo-classificaja.png',
    badge: data.badge || '/favicon.png',
    image: data.image || undefined,
    tag: data.tag || 'classificaja-notification',
    renotify: false,
    data: { url: data.url || '/' },
    actions: [{ action: 'open', title: data.actionTitle || 'Abrir no ClassificaJá' }],
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = new URL(event.notification?.data?.url || '/', self.location.origin).href;
  event.waitUntil((async () => {
    const clientsList = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clientsList) {
      if ('focus' in client) {
        try { await client.navigate(target); } catch {}
        return client.focus();
      }
    }
    if (clients.openWindow) return clients.openWindow(target);
  })());
});
