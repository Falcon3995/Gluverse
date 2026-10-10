import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import CGMSettings from './CGMSettings';
import { api } from '../api';

jest.mock('../api', () => ({
  api: { get: jest.fn() },
}));

test('renders the unavailable CGM state without implying live connectivity', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.get.mockResolvedValue({ message: 'CGM sync is unavailable in this environment.' });
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => root.render(<CGMSettings />));

  expect(api.get).toHaveBeenCalledWith('/api/cgm/status');
  expect(container.textContent).toContain('CGM sync is unavailable in this environment.');
  expect(container.textContent).toContain('does not provide emergency medical care');

  await act(async () => root.unmount());
});
