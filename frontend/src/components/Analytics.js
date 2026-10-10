import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

const dateRangeOptions = [
  { label: '7 Days', value: '7D' },
  { label: '14 Days', value: '14D' },
  { label: '30 Days', value: '30D' },
  { label: '90 Days', value: '90D' },
  { label: 'All Time', value: 'All Time' },
];

const Analytics = ({ userId }) => {
  const [selectedDateRange, setSelectedDateRange] = useState('7D');
  const [analyticsData, setAnalyticsData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadAnalytics = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setAnalyticsData(await api.get(`/api/analytics/glucose/${userId}?date_range=${selectedDateRange}`));
    } catch (err) {
      setError(err.message || 'Failed to load analytics.');
      setAnalyticsData(null);
    } finally {
      setLoading(false);
    }
  }, [selectedDateRange, userId]);

  useEffect(() => {
    loadAnalytics();
  }, [loadAnalytics]);

  if (loading) return <div className="analytics-container loading-state" role="status"><p>Loading analytics...</p><div className="spinner"></div></div>;

  return (
    <div className="analytics-container">
      <div className="page-header">
        <div>
          <h2>Analytics</h2>
          <p>Metrics are calculated from saved glucose readings.</p>
        </div>
        <div className="date-range-selector">
          <label htmlFor="date-range">View</label>
          <select id="date-range" value={selectedDateRange} onChange={(e) => setSelectedDateRange(e.target.value)}>
            {dateRangeOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>
      </div>

      {error && <p className="error-message" role="alert">{error}</p>}
      {analyticsData?.readings_count === 0 ? (
        <div className="empty-state-analytics" role="status">
          <p>{analyticsData.message}</p>
          <p>Log glucose readings to populate analytics.</p>
        </div>
      ) : analyticsData && (
        <>
          <div className="dashboard-grid">
            <div className="stat-card"><span className="label">Average</span><div className="value">{analyticsData.average_glucose}</div></div>
            <div className="stat-card"><span className="label">Readings</span><div className="value">{analyticsData.readings_count}</div></div>
            <div className="stat-card"><span className="label">Time In Range</span><div className="value">{analyticsData.time_in_range_percent}%</div></div>
            <div className="stat-card"><span className="label">Lows</span><div className="value">{analyticsData.low_count}</div></div>
            <div className="stat-card"><span className="label">Highs</span><div className="value">{analyticsData.high_count}</div></div>
            <div className="stat-card"><span className="label">Stale</span><div className="value">{analyticsData.stale_data_count}</div></div>
          </div>

          <section className="data-section">
            <h3>Trend By Day</h3>
            <div className="item-list">
              {analyticsData.trend_by_day.map((day) => (
                <article className="list-item" key={day.date}>
                  <div>
                    <h4>{day.date}</h4>
                    <p>Average {day.average_glucose} mg/dL across {day.readings} readings</p>
                  </div>
                  <div className="mini-bar"><span style={{ width: `${Math.min(100, day.average_glucose / 2)}%` }} /></div>
                </article>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
};

export default Analytics;
