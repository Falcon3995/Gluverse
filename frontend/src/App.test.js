import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import App, { AppErrorBoundary, LoginScreen, ProtectedRoute } from './App';

test('login screen switches between sign-in and account creation modes', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => root.render(<LoginScreen onLogin={() => {}} />));
  expect(container.querySelector('button[type="submit"]').textContent).toBe('Sign In');

  await act(async () => container.querySelectorAll('.segmented-control button')[1].click());
  expect(container.querySelector('button[type="submit"]').textContent).toBe('Create Account');

  await act(async () => root.unmount());
});

test('protected route redirects signed-out users to login', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => root.render(
    <MemoryRouter
      initialEntries={['/private']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route path="/" element={<p>Login destination</p>} />
        <Route path="/private" element={<ProtectedRoute currentUser={null}><p>Private content</p></ProtectedRoute>} />
      </Routes>
    </MemoryRouter>
  ));

  expect(container.textContent).toContain('Login destination');
  expect(container.textContent).not.toContain('Private content');
  await act(async () => root.unmount());
});

test('expired session returns the app to sign-in', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
  global.fetch = jest.fn().mockResolvedValue({
    ok: false,
    status: 401,
    url: 'http://localhost/api/auth/me',
    text: async () => JSON.stringify({ error: { message: 'Not authenticated.' } }),
    headers: { get: () => '' },
  });
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => root.render(<App />));

  expect(container.querySelector('button[type="submit"]').textContent).toBe('Sign In');
  await act(async () => root.unmount());
  warnSpy.mockRestore();
});

test('error boundary gives a recoverable user-facing message', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement('div');
  const root = createRoot(container);
  const BrokenChild = () => { throw new Error('test failure'); };
  const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

  await act(async () => root.render(<AppErrorBoundary><BrokenChild /></AppErrorBoundary>));

  expect(container.textContent).toContain('Something went wrong');
  expect(container.textContent).toContain('Please refresh or sign in again.');
  errorSpy.mockRestore();
  await act(async () => root.unmount());
});
