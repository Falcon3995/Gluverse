import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import Sidebar from './Sidebar';

test('provides an accessible collapsible navigation menu', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => {
    root.render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Sidebar onLogout={() => {}} />
      </MemoryRouter>
    );
  });

  const toggle = container.querySelector('.sidebar-menu-toggle');
  expect(toggle.textContent).toBe('Menu');
  expect(toggle.getAttribute('aria-expanded')).toBe('false');
  expect(container.querySelectorAll('.sidebar-nav a')).toHaveLength(12);
  expect(container.querySelector('a[href="/settings/cgm"]')).not.toBeNull();

  await act(async () => toggle.click());
  expect(toggle.getAttribute('aria-expanded')).toBe('true');
  await act(async () => container.querySelector('.sidebar-nav a').click());
  expect(toggle.getAttribute('aria-expanded')).toBe('false');

  await act(async () => root.unmount());
});
