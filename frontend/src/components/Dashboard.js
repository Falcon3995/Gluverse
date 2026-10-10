import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

const initialGlucoseForm = {
  value: '',
  notes: '',
  symptoms: '',
  context: '',
};

export const isValidGlucoseValue = (value) => {
  const number = Number(value);
  return Number.isFinite(number) && number >= 20 && number <= 600;
};

const Dashboard = ({ currentUser }) => {
  const navigate = useNavigate();
  const [latest, setLatest] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [meals, setMeals] = useState([]);
  const [insulin, setInsulin] = useState([]);
  const [alertState, setAlertState] = useState(null);
  const [glucoseForm, setGlucoseForm] = useState(initialGlucoseForm);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [latestResult, analyticsResult, mealsResult, insulinResult, alertResult] = await Promise.allSettled([
        api.get(`/api/glucose/latest/${currentUser.id}`),
        api.get(`/api/analytics/glucose/${currentUser.id}?date_range=7D`),
        api.get(`/api/meals/${currentUser.id}`),
        api.get(`/api/insulin/${currentUser.id}`),
        api.get(`/api/alerts/evaluate/${currentUser.id}`),
      ]);

      setLatest(latestResult.status === 'fulfilled' ? latestResult.value : null);
      setAnalytics(analyticsResult.status === 'fulfilled' ? analyticsResult.value : null);
      setMeals(mealsResult.status === 'fulfilled' ? mealsResult.value : []);
      setInsulin(insulinResult.status === 'fulfilled' ? insulinResult.value : []);
      setAlertState(alertResult.status === 'fulfilled' ? alertResult.value.alert : null);
      const failures = [latestResult, analyticsResult, mealsResult, insulinResult, alertResult].filter((result) => result.status === 'rejected');
      if (failures.length) {
        setError(failures[0].reason?.message || 'Some dashboard data could not be loaded.');
      }
    } catch (err) {
      setError(err.message || 'Dashboard failed to load.');
    } finally {
      setLoading(false);
    }
  }, [currentUser.id]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  const handleGlucoseSubmit = async (event) => {
    event.preventDefault();
    if (!isValidGlucoseValue(glucoseForm.value)) {
      setError('Enter a glucose value between 20 and 600 mg/dL.');
      setSuccess('');
      return;
    }
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await api.post(`/api/glucose/${currentUser.id}`, {
        ...glucoseForm,
        value: Number(glucoseForm.value),
        source: 'manual',
        timestamp: new Date().toISOString(),
      });
      setGlucoseForm(initialGlucoseForm);
      setSuccess('Glucose reading saved.');
      await loadDashboard();
    } catch (err) {
      setError(err.message || 'Unable to save glucose reading.');
    } finally {
      setSaving(false);
    }
  };

  const archiveLatest = async () => {
    if (!latest?.id) return;
    setSaving(true);
    setError('');
    try {
      await api.delete(`/api/glucose/${latest.id}`);
      setSuccess('Reading archived.');
      await loadDashboard();
    } catch (err) {
      setError(err.message || 'Unable to archive reading.');
    } finally {
      setSaving(false);
    }
  };

  const today = new Date().toDateString();
  const mealsToday = meals.filter((meal) => new Date(meal.timestamp).toDateString() === today);
  const insulinToday = insulin.filter((log) => new Date(log.timestamp).toDateString() === today);
  const totalCarbs = mealsToday.reduce((sum, meal) => sum + Number(meal.carbs || 0), 0);
  const totalInsulin = insulinToday.reduce((sum, log) => sum + Number(log.units || 0), 0);

  if (loading) {
    return <div className="dashboard-container loading-state" role="status"><p>Loading dashboard...</p><div className="spinner"></div></div>;
  }

  return (
    <div className="dashboard-container">
      <div className="page-header">
        <div>
          <h2>Dashboard</h2>
          <p>Welcome back, {currentUser.username}. Your dashboard uses saved glucose, meal, insulin, and alert data.</p>
        </div>
        <button type="button" onClick={loadDashboard}>Retry</button>
      </div>

      {error && <p className="error-message" role="alert">{error}</p>}
      {success && <p className="success-message" role="status">{success}</p>}

      {alertState?.triggered && (
        <div className="emergency-banner urgent">
          <h3>{alertState.reason}: {alertState.value} mg/dL</h3>
          <p>Triggered from reading at {new Date(alertState.source_timestamp).toLocaleString()}.</p>
          <button type="button" onClick={() => navigate('/emergency')}>Open Emergency Guidance</button>
        </div>
      )}

      {latest?.is_stale ? (
        <div className="stale-data-warning">
          <h3>Data is stale</h3>
          <p>Last reading was {latest.value} mg/dL at {new Date(latest.timestamp).toLocaleString()}.</p>
          <p>Log a new manual reading before relying on urgent alerts.</p>
          <button type="button" className="btn-dismiss-stale" onClick={archiveLatest} disabled={saving}>Archive Reading</button>
        </div>
      ) : latest ? (
        <div className="glucose-display">
          <span className="eyebrow">{latest.freshness_label || 'Recent'} reading</span>
          <h3>{latest.value} mg/dL</h3>
          <p>Last updated: {new Date(latest.timestamp).toLocaleString()}</p>
          <p>Source: {latest.source || 'manual'}</p>
        </div>
      ) : (
        <div className="empty-state" role="status">
          <p>No glucose readings yet. Log your first reading to activate dashboard stats.</p>
        </div>
      )}

        <form className="form-card" onSubmit={handleGlucoseSubmit} aria-busy={saving}>
        <h3>Log Glucose</h3>
        <div className="form-grid">
          <label>
            Value mg/dL
            <input
              type="number"
              inputMode="decimal"
              min="20"
              max="600"
              value={glucoseForm.value}
              onChange={(event) => setGlucoseForm({ ...glucoseForm, value: event.target.value })}
              required
            />
          </label>
          <label>
            Symptoms
            <input
              value={glucoseForm.symptoms}
              onChange={(event) => setGlucoseForm({ ...glucoseForm, symptoms: event.target.value })}
              placeholder="Optional"
            />
          </label>
          <label>
            Context
            <input
              value={glucoseForm.context}
              onChange={(event) => setGlucoseForm({ ...glucoseForm, context: event.target.value })}
              placeholder="Before meal, exercise..."
            />
          </label>
          <label>
            Notes
            <input
              value={glucoseForm.notes}
              onChange={(event) => setGlucoseForm({ ...glucoseForm, notes: event.target.value })}
              placeholder="Optional"
            />
          </label>
        </div>
        <button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save Reading'}</button>
      </form>

      <div className="dashboard-grid">
        <div className="stat-card"><span className="label">Meals Today</span><div className="value">{mealsToday.length}</div></div>
        <div className="stat-card"><span className="label">Carbs Today</span><div className="value">{totalCarbs}g</div></div>
        <div className="stat-card"><span className="label">Insulin Today</span><div className="value">{totalInsulin}u</div></div>
        <div className="stat-card"><span className="label">Avg Glucose 7D</span><div className="value">{analytics?.readings_count ? analytics.average_glucose : '--'}</div></div>
        <div className="stat-card"><span className="label">Time In Range</span><div className="value">{analytics?.readings_count ? `${analytics.time_in_range_percent}%` : '--'}</div></div>
        <div className="stat-card" role="status"><span className="label">Alerts</span><div className="value">{alertState?.triggered ? alertState.severity : 'Clear'}</div></div>
      </div>

      <div className="quick-actions">
        <button type="button" onClick={() => navigate('/log-meal')}>Log Meal</button>
        <button type="button" onClick={() => navigate('/insulin')}>Log Insulin</button>
        <button type="button" onClick={() => navigate('/meal-history')}>Meal History</button>
        <button type="button" onClick={() => navigate('/emergency')}>Emergency Guidance</button>
      </div>
    </div>
  );
};

export default Dashboard;
