import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

const emptyLog = {
  insulin_type: 'bolus',
  units: '',
  linked_meal_id: '',
  notes: '',
};

export const isValidInsulinUnits = (value) => {
  const units = Number(value);
  return Number.isFinite(units) && units >= 0;
};

const InsulinLog = ({ currentUser }) => {
  const [form, setForm] = useState(emptyLog);
  const [logs, setLogs] = useState([]);
  const [meals, setMeals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [logData, mealData] = await Promise.all([
        api.get(`/api/insulin/${currentUser.id}`),
        api.get(`/api/meals/${currentUser.id}`),
      ]);
      setLogs(logData);
      setMeals(mealData);
    } catch (err) {
      setError(err.message || 'Unable to load insulin logs.');
    } finally {
      setLoading(false);
    }
  }, [currentUser.id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const submitLog = async (event) => {
    event.preventDefault();
    if (!isValidInsulinUnits(form.units)) {
      setError('Enter a valid nonnegative insulin amount.');
      setSuccess('');
      return;
    }
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/api/insulin/${currentUser.id}`, {
        ...form,
        units: Number(form.units),
        timestamp: new Date().toISOString(),
      });
      setForm(emptyLog);
      setSuccess('Insulin log saved.');
      await loadData();
    } catch (err) {
      setError(err.message || 'Unable to save insulin log.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="insulin-container">
      <div className="page-header">
        <div>
          <h2>Insulin Log</h2>
          <p>Track insulin events without calculating or recommending doses.</p>
        </div>
        <button type="button" onClick={loadData}>Retry</button>
      </div>

      <div className="info-banner" role="status">
        GluVerse records insulin entries for tracking only. It does not prescribe doses or calculate insulin-on-board.
      </div>
      {error && <p className="error-message" role="alert">{error}</p>}
      {success && <p className="success-message" role="status">{success}</p>}

      <form className="form-card" onSubmit={submitLog} aria-busy={saving}>
        <div className="form-grid">
          <label>
            Type
            <select value={form.insulin_type} onChange={(e) => setForm({ ...form, insulin_type: e.target.value })}>
              <option value="bolus">Bolus</option>
              <option value="basal">Basal</option>
              <option value="correction">Correction</option>
            </select>
          </label>
          <label>
            Units
            <input type="number" inputMode="decimal" min="0" step="0.1" value={form.units} onChange={(e) => setForm({ ...form, units: e.target.value })} required />
          </label>
          <label>
            Linked meal
            <select value={form.linked_meal_id} onChange={(e) => setForm({ ...form, linked_meal_id: e.target.value })}>
              <option value="">None</option>
              {meals.map((meal) => <option key={meal.id} value={meal.id}>{meal.name}</option>)}
            </select>
          </label>
          <label>
            Notes
            <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Optional" />
          </label>
        </div>
        <button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save Insulin Log'}</button>
      </form>

      <section className="data-section">
        <h3>Recent Insulin Logs</h3>
        {loading ? <p role="status">Loading logs...</p> : logs.length === 0 ? <p className="muted" role="status">No insulin logs yet.</p> : (
          <div className="item-list">
            {logs.map((log) => (
              <article key={log.id} className="list-item">
                <div>
                  <h4>{log.insulin_type} · {log.units}u</h4>
                  <p>{new Date(log.timestamp).toLocaleString()}</p>
                  {log.notes && <p>{log.notes}</p>}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export default InsulinLog;
