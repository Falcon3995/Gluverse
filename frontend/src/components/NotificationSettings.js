import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

const booleanFields = ['low_glucose_alert', 'high_glucose_alert', 'stale_data_alert', 'missed_meal_alert'];

export const hasInvalidThresholdOrder = (rules) => !(
  rules.urgent_low <= rules.low && rules.low < rules.high && rules.high <= rules.urgent_high
);

export const hasInvalidTargetRange = (profile) => profile.target_low >= profile.target_high;

const NotificationSettings = ({ currentUser }) => {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setSettings(await api.get(`/api/settings/${currentUser.id}`));
    } catch (err) {
      setError(err.message || 'Unable to load settings.');
    } finally {
      setLoading(false);
    }
  }, [currentUser.id]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const updateSection = (section, key, value) => {
    setSettings({ ...settings, [section]: { ...settings[section], [key]: value } });
  };

  const saveSettings = async (event) => {
    event.preventDefault();
    if (hasInvalidTargetRange(settings.profile)) {
      setError('Target low must be below target high.');
      setSuccess('');
      return;
    }
    if (hasInvalidThresholdOrder(settings.alert_rules)) {
      setError('Alert thresholds must be ordered from urgent low through urgent high.');
      setSuccess('');
      return;
    }
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const payload = {
        ...settings,
        notification_settings: Object.fromEntries(
          Object.entries(settings.notification_settings).map(([key, value]) => [key, booleanFields.includes(key) ? Number(Boolean(value)) : value])
        ),
      };
      await api.put(`/api/settings/${currentUser.id}`, payload);
      setSuccess('Settings saved.');
      await loadSettings();
    } catch (err) {
      setError(err.message || 'Unable to save settings.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="settings-container loading-state" role="status"><p>Loading notification settings...</p><div className="spinner"></div></div>;
  }

  if (!settings) {
    return <div className="settings-container error-state"><p className="error-message" role="alert">{error || 'Settings unavailable.'}</p><button type="button" onClick={loadSettings}>Retry</button></div>;
  }

  return (
    <div className="settings-container">
      <div className="page-header">
        <div>
          <h2>Alerts & Settings</h2>
          <p>Configure profile, alert thresholds, and in-app notification preferences.</p>
        </div>
        <button type="button" onClick={loadSettings}>Retry</button>
      </div>

      {error && <p className="error-message" role="alert">{error}</p>}
      {success && <p className="success-message" role="status">{success}</p>}

      <form className="form-card" onSubmit={saveSettings}>
        <h3>Profile</h3>
        <div className="form-grid">
          <label>Name<input value={settings.profile.username || ''} onChange={(e) => updateSection('profile', 'username', e.target.value)} /></label>
          <label>Diabetes type<input value={settings.profile.diabetes_type || ''} onChange={(e) => updateSection('profile', 'diabetes_type', e.target.value)} /></label>
          <label>Units<select value={settings.profile.units || 'mg/dL'} onChange={(e) => updateSection('profile', 'units', e.target.value)}><option>mg/dL</option></select></label>
          <label>Target low<input type="number" inputMode="decimal" min="40" max="250" value={settings.profile.target_low || 70} onChange={(e) => updateSection('profile', 'target_low', Number(e.target.value))} /></label>
          <label>Target high<input type="number" inputMode="decimal" min="50" max="350" value={settings.profile.target_high || 180} onChange={(e) => updateSection('profile', 'target_high', Number(e.target.value))} /></label>
        </div>

        <h3>Alert Rules</h3>
        <div className="form-grid">
          <label>Urgent low<input type="number" inputMode="decimal" min="40" max="120" value={settings.alert_rules.urgent_low} onChange={(e) => updateSection('alert_rules', 'urgent_low', Number(e.target.value))} /></label>
          <label>Low<input type="number" inputMode="decimal" min="40" max="150" value={settings.alert_rules.low} onChange={(e) => updateSection('alert_rules', 'low', Number(e.target.value))} /></label>
          <label>High<input type="number" inputMode="decimal" min="90" max="350" value={settings.alert_rules.high} onChange={(e) => updateSection('alert_rules', 'high', Number(e.target.value))} /></label>
          <label>Urgent high<input type="number" inputMode="decimal" min="120" max="500" value={settings.alert_rules.urgent_high} onChange={(e) => updateSection('alert_rules', 'urgent_high', Number(e.target.value))} /></label>
          <label>Stale minutes<input type="number" inputMode="decimal" min="5" max="1440" value={settings.alert_rules.stale_minutes} onChange={(e) => updateSection('alert_rules', 'stale_minutes', Number(e.target.value))} /></label>
          <label>Missed meal hours<input type="number" inputMode="decimal" min="1" max="48" value={settings.alert_rules.missed_meal_hours} onChange={(e) => updateSection('alert_rules', 'missed_meal_hours', Number(e.target.value))} /></label>
        </div>

        <h3>In-App Notification Preferences</h3>
        <div className="toggle-grid">
          {booleanFields.map((field) => (
            <label key={field} className="toggle-row">
              <input
                type="checkbox"
                checked={Boolean(settings.notification_settings[field])}
                onChange={(e) => updateSection('notification_settings', field, e.target.checked)}
              />
              {field.replaceAll('_', ' ')}
            </label>
          ))}
        </div>

        <div className="row-actions">
          <button type="submit" disabled={saving}>{saving ? 'Saving...' : 'Save Settings'}</button>
        </div>
      </form>
    </div>
  );
};

export default NotificationSettings;
