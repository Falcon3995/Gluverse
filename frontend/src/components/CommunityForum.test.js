import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import CommunityForum from './CommunityForum';
import { api } from '../api';

jest.mock('../api', () => ({
  api: { get: jest.fn(), post: jest.fn() },
}));

test('renders the empty forum state and disables blank posts', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.get.mockResolvedValue([]);
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => root.render(<CommunityForum currentUser={{ id: 'user-1', username: 'Test' }} isAdmin={false} />));

  expect(container.textContent).toContain('No posts yet. Be the first to share!');
  expect(container.querySelector('button[type="submit"]').disabled).toBe(true);
  expect(api.post).not.toHaveBeenCalled();

  await act(async () => root.unmount());
});
