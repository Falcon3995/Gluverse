import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Analytics from './Analytics';
import { api } from '../api';

jest.mock('../api', () => ({
  api: { get: jest.fn() },
}));

test('renders the analytics empty state for a selected range', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.get.mockResolvedValue({
    readings_count: 0,
    message: 'No readings found for this range.',
  });
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => root.render(<Analytics userId="user-1" />));

  expect(api.get).toHaveBeenCalledWith('/api/analytics/glucose/user-1?date_range=7D');
  expect(container.textContent).toContain('No readings found for this range.');
  expect(container.textContent).toContain('Log glucose readings to populate analytics.');

  await act(async () => root.unmount());
});
