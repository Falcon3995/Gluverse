import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

const CGMSettings = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const cgmStatus = await api.get('/api/cgm/status');
      setStatus(cgmStatus);
    } catch (err) {
      setError(err.message || 'Unable to load CGM status.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  if (loading) {
    return <div className="cgm-settings-container loading-state" role="status"><p>Loading CGM status...</p><div className="spinner"></div></div>;
  }

  return (
    <div className="cgm-settings-container">
      <div className="page-header">
        <div>
          <h2>CGM</h2>
          <p>Production CGM sync is disabled for this release.</p>
        </div>
        <button type="button" onClick={loadStatus}>Retry</button>
      </div>

      {error && <p className="error-message" role="alert">{error}</p>}
      <div className="info-banner" role="status">
        {status?.message || 'Dexcom sync is not enabled in this environment. Log glucose manually instead.'}
      </div>
      <p className="disclaimer">CGM data is not connected here. GluVerse does not provide emergency medical care.</p>
    </div>
  );
};

export default CGMSettings;
