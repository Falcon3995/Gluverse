import { hasIncompleteContact } from './EmergencyGuidance';

test('detects emergency contacts missing either a name or phone number', () => {
  expect(hasIncompleteContact([{ name: 'Casey', phone: '' }])).toBe(true);
  expect(hasIncompleteContact([{ name: 'Casey', phone: '555-0101' }])).toBe(false);
  expect(hasIncompleteContact([{ name: '', phone: '' }])).toBe(false);
});
