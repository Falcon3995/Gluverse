import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Achievements from './Achievements';
import { api } from '../api';

jest.mock('../api', () => ({
  api: { get: jest.fn() },
}));

test('renders the empty achievements state for a new user', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.get.mockResolvedValue({
    achievements_progress: {},
    earned_achievements: [],
    meal_counts: { total_meals_logged: 0 },
    streaks: { glucose_log_streak: 0 },
  });
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => root.render(<Achievements userId="user-1" />));

  expect(api.get).toHaveBeenCalledWith('/api/achievements/progress/user-1');
  expect(container.textContent).toContain('No achievements earned yet!');
  expect(container.textContent).toContain('Total meals logged: 0');

  await act(async () => root.unmount());
});
