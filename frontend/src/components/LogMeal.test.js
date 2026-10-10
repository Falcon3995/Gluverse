import { hasInvalidMealNumbers } from './LogMeal';

test('rejects negative or non-numeric meal nutrition values', () => {
  expect(hasInvalidMealNumbers({ carbs: 30, protein: 10, fat: 5, calories: 250 })).toBe(false);
  expect(hasInvalidMealNumbers({ carbs: -1, protein: 10, fat: 5, calories: 250 })).toBe(true);
  expect(hasInvalidMealNumbers({ carbs: 'not-a-number', protein: 10, fat: 5, calories: 250 })).toBe(true);
});
