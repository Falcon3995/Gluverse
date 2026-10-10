import { api, apiRequest } from './api';

const response = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  url: 'http://localhost/api/test',
  text: async () => JSON.stringify(body),
});

beforeEach(() => {
  global.fetch = jest.fn();
  jest.spyOn(console, 'warn').mockImplementation(() => {});
  document.cookie = 'gluverse_csrf=; Max-Age=0';
});

afterEach(() => {
  jest.restoreAllMocks();
});

test('login posts credentials with the session cookie enabled', async () => {
  fetch.mockResolvedValue(response(200, { user: { id: 'user-1' } }));

  await api.post('/api/auth/login', { username: 'test', password: 'secret' });

  expect(fetch).toHaveBeenCalledWith('/api/auth/login', expect.objectContaining({
    method: 'POST',
    credentials: 'include',
    body: JSON.stringify({ username: 'test', password: 'secret' }),
  }));
});

test('glucose writes include the CSRF cookie', async () => {
  document.cookie = 'gluverse_csrf=csrf-token';
  fetch.mockResolvedValue(response(201, { id: 'reading-1' }));

  await api.post('/api/glucose/user-1', { value: 120 });

  expect(fetch.mock.calls[0][1].headers['X-CSRF-Token']).toBe('csrf-token');
});

test('an expired session notifies the app', async () => {
  const expired = jest.fn();
  window.addEventListener('gluverse-auth-expired', expired, { once: true });
  fetch.mockResolvedValue(response(401, { error: { message: 'Not authenticated.' } }));

  await expect(apiRequest('/api/auth/me')).rejects.toMatchObject({
    message: 'Not authenticated.',
    category: 'auth/session',
  });
  expect(expired).toHaveBeenCalledTimes(1);
});

test('API errors preserve their user-facing message and category', async () => {
  fetch.mockResolvedValue(response(403, { error: { message: 'CSRF token missing or invalid.' } }));

  await expect(api.post('/api/glucose/user-1', { value: 120 })).rejects.toMatchObject({
    message: 'CSRF token missing or invalid.',
    category: 'csrf',
  });
});
