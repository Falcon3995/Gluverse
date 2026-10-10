const API_BASE = process.env.REACT_APP_API_BASE_URL || '';
const REQUEST_TIMEOUT_MS = 15000;
const IS_DEV = process.env.NODE_ENV !== 'production';
let firstAuthFailure = null;

function requestId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getCookie(name) {
  if (typeof document === 'undefined') return '';
  return document.cookie.split('; ').reduce((match, pair) => {
    if (pair.startsWith(`${name}=`)) {
      return decodeURIComponent(pair.slice(name.length + 1));
    }
    return match;
  }, '');
}

function classifyApiError({ status, path, message }) {
  const lowerMessage = (message || '').toLowerCase();
  if (status === 401 || lowerMessage.includes('not authenticated') || lowerMessage.includes('invalid credentials')) {
    return 'auth/session';
  }
  if (status === 403 && lowerMessage.includes('csrf')) {
    return 'csrf';
  }
  if (status === 403) {
    if (path.includes('/notifications/') || path.includes('/cgm/') || lowerMessage.includes('unavailable on your current plan')) {
      return 'feature-gated';
    }
    return 'forbidden';
  }
  return 'error';
}

function emitApiFailure(detail) {
  if (!IS_DEV || typeof window === 'undefined') return;
  if (!firstAuthFailure && detail.phase === 'post-auth') {
    firstAuthFailure = detail;
  }
  const payload = firstAuthFailure || detail;
  window.dispatchEvent(new CustomEvent('gluverse-api-failure', { detail: payload }));
  // Helpful when debugging with the browser console.
  console.warn('[gluverse-api-failure]', payload);
}

export function clearApiFailureTrace() {
  firstAuthFailure = null;
  if (IS_DEV && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('gluverse-api-failure-clear'));
  }
}

export async function apiRequest(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const method = (options.method || 'GET').toUpperCase();
    const response = await fetch(`${API_BASE}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': requestId(),
        ...(method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS' ? { 'X-CSRF-Token': getCookie('gluverse_csrf') } : {}),
        ...(options.headers || {}),
      },
      credentials: 'include',
      signal: controller.signal,
      ...options,
    });

    const text = await response.text();
    let data = null;
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { message: text };
      }
    }

    if (!response.ok) {
      const message = data?.message || data?.error?.message || `Request failed with status ${response.status}`;
      const failure = {
        status: response.status,
        method,
        path,
        url: response.url,
        message,
        category: classifyApiError({ status: response.status, path, message }),
        phase: method === 'POST' && (path === '/api/auth/login' || path === '/api/auth/register') ? 'auth' : 'post-auth',
        timestamp: new Date().toISOString(),
      };
      emitApiFailure(failure);
      if (response.status === 401) {
        window.dispatchEvent(new Event('gluverse-auth-expired'));
      }
      const error = new Error(message);
      error.status = response.status;
      error.url = response.url;
      error.path = path;
      error.category = failure.category;
      error.response = data;
      error.requestId = response.headers?.get?.('X-Request-ID') || data?.request_id || '';
      throw error;
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') {
      const timeoutError = new Error('Request timed out. Please try again.');
      timeoutError.category = 'timeout';
      timeoutError.path = path;
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  get: (path) => apiRequest(path),
  post: (path, body) => apiRequest(path, { method: 'POST', body: JSON.stringify(body) }),
  put: (path, body) => apiRequest(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: (path) => apiRequest(path, { method: 'DELETE' }),
};
