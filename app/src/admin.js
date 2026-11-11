/**
 * SGIP - Hidden Administrative Portal Controller
 */

export function isAdminRouteRequested() {
  if (typeof window === 'undefined') return false;
  const path = window.location.pathname.toLowerCase();
  const hash = window.location.hash.toLowerCase();
  return path === '/admin' || path.startsWith('/admin/') || hash === '#admin';
}

export function initAdmin(store) {
  if (!isAdminRouteRequested()) {
    return;
  }
  // Base initialization for modular frontend
  console.info('Admin route requested:', window.location.pathname);
}
