import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

const emptyMeal = {
  name: '',
  carbs: '',
  protein: '',
  fat: '',
  calories: '',
  notes: '',
  photo_url: '',
};

export const hasInvalidMealNumbers = (meal) => ['carbs', 'protein', 'fat', 'calories']
  .some((field) => !Number.isFinite(Number(meal[field] || 0)) || Number(meal[field] || 0) < 0);

const LogMeal = ({ currentUser }) => {
  const [meal, setMeal] = useState(emptyMeal);
  const [recentMeals, setRecentMeals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const loadMeals = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setRecentMeals(await api.get(`/api/meals/${currentUser.id}`));
    } catch (err) {
      setError(err.message || 'Unable to load meals.');
    } finally {
      setLoading(false);
    }
  }, [currentUser.id]);

  useEffect(() => {
    loadMeals();
  }, [loadMeals]);

  const submitMeal = async (event) => {
    event.preventDefault();
    if (hasInvalidMealNumbers(meal)) {
      setError('Meal nutrition values must be zero or greater.');
      setSuccess('');
      return;
    }
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/api/meals/${currentUser.id}`, {
        ...meal,
        carbs: Number(meal.carbs || 0),
        protein: Number(meal.protein || 0),
        fat: Number(meal.fat || 0),
        calories: Number(meal.calories || 0),
        timestamp: new Date().toISOString(),
        notes: meal.notes,
      });
      setMeal(emptyMeal);
      setSuccess('Meal saved.');
      await loadMeals();
    } catch (err) {
      setError(err.message || 'Unable to save meal.');
    } finally {
      setSaving(false);
    }
  };

  const deleteMeal = async (mealId) => {
    setError('');
    try {
      await api.delete(`/api/meals/${mealId}`);
      await loadMeals();
    } catch (err) {
      setError(err.message || 'Unable to delete meal.');
    }
  };

  return (
    <div className="meal-page-container">
      <div className="page-header">
        <div>
          <h2>Log Meal</h2>
          <p>Save meal details to power dashboard stats and analytics.</p>
        </div>
        <button type="button" onClick={loadMeals}>Retry</button>
      </div>

      {error && <p className="error-message" role="alert">{error}</p>}
      {success && <p className="success-message" role="status">{success}</p>}

      <form className="form-card" onSubmit={submitMeal} aria-busy={saving}>
        <div className="form-grid">
          <label>Meal name<input value={meal.name} onChange={(e) => setMeal({ ...meal, name: e.target.value })} required /></label>
          <label>Carbs g<input type="number" inputMode="decimal" min="0" step="0.1" value={meal.carbs} onChange={(e) => setMeal({ ...meal, carbs: e.target.value })} /></label>
          <label>Protein g<input type="number" inputMode="decimal" min="0" step="0.1" value={meal.protein} onChange={(e) => setMeal({ ...meal, protein: e.target.value })} /></label>
          <label>Fat g<input type="number" inputMode="decimal" min="0" step="0.1" value={meal.fat} onChange={(e) => setMeal({ ...meal, fat: e.target.value })} /></label>
          <label>Calories<input type="number" inputMode="decimal" min="0" value={meal.calories} onChange={(e) => setMeal({ ...meal, calories: e.target.value })} /></label>
          <label>Photo URL<input value={meal.photo_url} onChange={(e) => setMeal({ ...meal, photo_url: e.target.value })} placeholder="Optional" /></label>
        </div>
        <label className="full-width">Notes<textarea value={meal.notes} onChange={(e) => setMeal({ ...meal, notes: e.target.value })} /></label>
        <button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save Meal'}</button>
      </form>

      <section className="data-section">
        <h3>Recent Meals</h3>
        {loading ? <p role="status">Loading meals...</p> : recentMeals.length === 0 ? (
          <p className="muted">No meals logged yet.</p>
        ) : (
          <div className="item-list">
            {recentMeals.slice(0, 5).map((item) => (
              <article className="list-item" key={item.id}>
                <div>
                  <h4>{item.name}</h4>
                  <p>{new Date(item.timestamp).toLocaleString()}</p>
                  <p>{item.carbs}g carbs, {item.protein}g protein, {item.fat}g fat, {item.calories} calories</p>
                </div>
                <button type="button" className="btn-delete" onClick={() => deleteMeal(item.id)}>Delete</button>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export default LogMeal;
