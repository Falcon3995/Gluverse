import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

export const hasInvalidMealEditNumbers = (meal) => ['carbs', 'protein', 'fat', 'calories']
  .some((field) => !Number.isFinite(Number(meal[field] || 0)) || Number(meal[field] || 0) < 0);

const MealHistory = ({ currentUser }) => {
  const [meals, setMeals] = useState([]);
  const [editingId, setEditingId] = useState('');
  const [draft, setDraft] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadMealHistory = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setMeals(await api.get(`/api/meals/${currentUser.id}`));
    } catch (err) {
      setError(err.message || 'Failed to load meal history.');
    } finally {
      setLoading(false);
    }
  }, [currentUser.id]);

  useEffect(() => {
    loadMealHistory();
  }, [loadMealHistory]);

  const startEdit = (meal) => {
    setEditingId(meal.id);
    setDraft({ ...meal });
  };

  const saveEdit = async () => {
    if (hasInvalidMealEditNumbers(draft)) {
      setError('Meal nutrition values must be zero or greater.');
      return;
    }
    setError('');
    try {
      await api.put(`/api/meals/${editingId}`, draft);
      setEditingId('');
      setDraft({});
      await loadMealHistory();
    } catch (err) {
      setError(err.message || 'Unable to update meal.');
    }
  };

  const deleteMeal = async (mealId) => {
    setError('');
    try {
      await api.delete(`/api/meals/${mealId}`);
      await loadMealHistory();
    } catch (err) {
      setError(err.message || 'Unable to delete meal.');
    }
  };

  if (loading) {
    return <div className="meal-history-container loading-state" role="status"><p>Loading meal history...</p><div className="spinner"></div></div>;
  }

  return (
    <div className="meal-history-container">
      <div className="page-header">
        <div>
          <h2>Meal History</h2>
          <p>Review, edit, or delete saved meal logs.</p>
        </div>
        <button type="button" onClick={loadMealHistory}>Retry</button>
      </div>
      {error && <p className="error-message" role="alert">{error}</p>}
      {meals.length === 0 ? (
        <div className="empty-state" role="status"><p>No meals logged yet.</p></div>
      ) : (
        <div className="item-list">
          {meals.map((meal) => (
            <article key={meal.id} className="list-item">
              {editingId === meal.id ? (
                <div className="edit-grid">
                  <input aria-label="Meal name" value={draft.name || ''} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                  <input aria-label="Carbohydrates in grams" type="number" min="0" step="0.1" value={draft.carbs || 0} onChange={(e) => setDraft({ ...draft, carbs: Number(e.target.value) })} />
                  <input aria-label="Protein in grams" type="number" min="0" step="0.1" value={draft.protein || 0} onChange={(e) => setDraft({ ...draft, protein: Number(e.target.value) })} />
                  <input aria-label="Fat in grams" type="number" min="0" step="0.1" value={draft.fat || 0} onChange={(e) => setDraft({ ...draft, fat: Number(e.target.value) })} />
                  <textarea aria-label="Meal notes" value={draft.notes || ''} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
                  <div className="row-actions">
                    <button type="button" onClick={saveEdit}>Save</button>
                    <button type="button" className="btn-moderate" onClick={() => setEditingId('')}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <div>
                    <h3>{meal.name}</h3>
                    <p>{new Date(meal.timestamp).toLocaleString()}</p>
                    <p>{meal.carbs}g carbs, {meal.protein}g protein, {meal.fat}g fat, {meal.calories} calories</p>
                    {meal.notes && <p>{meal.notes}</p>}
                  </div>
                  <div className="row-actions">
                    <button type="button" onClick={() => startEdit(meal)}>Edit</button>
                    <button type="button" className="btn-delete" onClick={() => deleteMeal(meal.id)}>Delete</button>
                  </div>
                </>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
};

export default MealHistory;
