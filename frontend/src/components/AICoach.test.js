import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import AICoach from './AICoach';
import { api } from '../api';

jest.mock('../api', () => ({
  api: { post: jest.fn() },
}));

test('renders the safety boundary and displays a coach response', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.post.mockResolvedValue({ reply: 'Review your saved patterns with your care team.', next_top_5: [] });
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => root.render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><AICoach currentUser={{ id: 'user-1' }} /></MemoryRouter>));
  expect(container.textContent).toContain('uses an external AI service');
  expect(container.textContent).toContain('Do not include names or other identifying details');
  expect(container.querySelector('button[type="submit"]').disabled).toBe(true);

  await act(async () => {
    const input = container.querySelector('#coach-message');
    const setInputValue = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setInputValue.call(input, 'What patterns should I discuss?');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    container.querySelector('form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  });

  expect(api.post).toHaveBeenCalledWith('/api/coach/respond', {
    user_id: 'user-1',
    message: 'What patterns should I discuss?',
  });
  expect(container.textContent).toContain('Review your saved patterns with your care team.');
  await act(async () => root.unmount());
});
