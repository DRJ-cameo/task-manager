// static/sw.js
// Minimal service worker that accepts a postMessage to show a notification.
self.addEventListener('install', (e) => {
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener('message', (event) => {
  try {
    const data = event.data || {};
    if (data && data.type === 'show-notification') {
      const title = data.title || 'Reminder';
      const options = data.options || {};
      self.registration.showNotification(title, options);
    }
  } catch (err) {
    // ignore
  }
});

// optional: respond to notification clicks
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  // try to focus an existing client or open the dashboard
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url && 'focus' in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow('/dashboard');
    })
  );
});
