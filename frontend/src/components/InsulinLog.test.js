import { isValidInsulinUnits } from './InsulinLog';

test('accepts nonnegative finite insulin amounts only', () => {
  expect(isValidInsulinUnits(2.5)).toBe(true);
  expect(isValidInsulinUnits('0')).toBe(true);
  expect(isValidInsulinUnits(-1)).toBe(false);
  expect(isValidInsulinUnits('not-a-number')).toBe(false);
});
