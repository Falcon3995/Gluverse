import { hasInvalidTargetRange, hasInvalidThresholdOrder } from './NotificationSettings';

test('detects contradictory alert threshold order', () => {
  expect(hasInvalidThresholdOrder({ urgent_low: 54, low: 70, high: 180, urgent_high: 250 })).toBe(false);
  expect(hasInvalidThresholdOrder({ urgent_low: 100, low: 80, high: 180, urgent_high: 250 })).toBe(true);
  expect(hasInvalidThresholdOrder({ urgent_low: 54, low: 70, high: 260, urgent_high: 250 })).toBe(true);
});

test('detects an invalid target glucose range', () => {
  expect(hasInvalidTargetRange({ target_low: 70, target_high: 180 })).toBe(false);
  expect(hasInvalidTargetRange({ target_low: 200, target_high: 100 })).toBe(true);
});
