import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import MealHistory, { hasInvalidMealEditNumbers } from './MealHistory';
import { api } from '../api';

jest.mock('../api', () => ({
  api: { get: jest.fn(), put: jest.fn(), delete: jest.fn() },
}));

test('rejects invalid nutrition values in meal edits', () => {
  expect(hasInvalidMealEditNumbers({ carbs: 'bad', protein: 0, fat: 0, calories: 0 })).toBe(true);
  expect(hasInvalidMealEditNumbers({ carbs: 20, protein: 5, fat: 3, calories: 180 })).toBe(false);
});

test('renders the empty meal history state', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.get.mockResolvedValue([]);
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => root.render(<MealHistory currentUser={{ id: 'user-1' }} />));

  expect(api.get).toHaveBeenCalledWith('/api/meals/user-1');
  expect(container.textContent).toContain('No meals logged yet.');
  await act(async () => root.unmount());
});
