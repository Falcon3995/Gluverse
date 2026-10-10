import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Shop, { hasInvalidRequestQuantity } from './Shop';
import { api } from '../api';

jest.mock('../api', () => ({
  api: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}));

test('accepts only whole-number request quantities from 1 to 99', () => {
  expect(hasInvalidRequestQuantity(0)).toBe(true);
  expect(hasInvalidRequestQuantity(1.5)).toBe(true);
  expect(hasInvalidRequestQuantity(99)).toBe(false);
});

test('renders the catalog and empty saved-request state', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  api.get
    .mockResolvedValueOnce([{ id: 'item-1', name: 'Test item', category: 'Care', description: 'Test', price: 4.5 }])
    .mockResolvedValueOnce([]);
  const container = document.createElement('div');
  const root = createRoot(container);

  await act(async () => root.render(<Shop currentUser={{ id: 'user-1' }} />));

  expect(api.get).toHaveBeenNthCalledWith(1, '/api/shop/catalog');
  expect(api.get).toHaveBeenNthCalledWith(2, '/api/shop/requests/user-1');
  expect(container.textContent).toContain('Test item');
  expect(container.textContent).toContain('No saved requests yet.');
  expect(container.querySelector('button').textContent).toBe('Refresh');

  await act(async () => root.unmount());
});
