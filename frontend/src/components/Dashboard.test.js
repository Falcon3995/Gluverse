import { isValidGlucoseValue } from './Dashboard';

test('accepts glucose values within the supported range only', () => {
  expect(isValidGlucoseValue(20)).toBe(true);
  expect(isValidGlucoseValue('600')).toBe(true);
  expect(isValidGlucoseValue(19)).toBe(false);
  expect(isValidGlucoseValue(601)).toBe(false);
  expect(isValidGlucoseValue('')).toBe(false);
});
