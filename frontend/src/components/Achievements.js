import React, { useState, useEffect } from 'react';
import { api } from '../api';

const achievementNames = {
  first_glucose: 'First Glucose Log',
  first_meal: 'First Meal Log',
  week_warrior: 'Week Warrior',
  meal_tracker: 'Meal Tracker',
  glucose_guardian: 'Glucose Guardian',
  range_ranger: 'Range Ranger',
  three_day: '3-Day Streak',
  seven_day: '7-Day Streak',
  ten_meals: '10 Meals',
  thirty_readings: '30 Readings',
};

const Achievements = ({ userId }) => {
  const [gamificationData, setGamificationData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadGamificationData = async () => {
      setLoading(true);
      setError(null);
      try {
        setGamificationData(await api.get(`/api/achievements/progress/${userId}`));
      } catch (err) {
        console.error("Failed to load achievements data:", err);
        setError("Failed to load achievements and progress. Please try again later.");
        setGamificationData(null);
      } finally {
        setLoading(false);
      }
    };

    loadGamificationData();
  }, [userId]);

  if (loading) {
    return (
      <div className="achievements-container loading-state" role="status">
        <p>Loading your achievements...</p>
        <div className="spinner"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="achievements-container error-state">
        <p className="error-message" role="alert">{error}</p>
      </div>
    );
  }

  // Handle empty state for all gamification data
  if (!gamificationData || (Object.keys(gamificationData.achievements_progress).length === 0 && gamificationData.earned_achievements.length === 0 && gamificationData.meal_counts.total_meals_logged === 0 && gamificationData.streaks.glucose_log_streak === 0)) {
    return (
      <div className="achievements-container empty-state" role="status">
        <h2>Your Achievements</h2>
        <p>No achievements earned yet!</p>
        <p>Start by logging your glucose and meals to unlock badges and track your progress.</p>
        <p>Glucose log streak: 0 days</p>
        <p>Total meals logged: 0</p>
      </div>
    );
  }

  return (
    <div className="achievements-container">
      <h2>Your Achievements</h2>

      <div className="gamification-summary">
        <h3>Current Progress</h3>
        <p>Glucose Log Streak: <strong>{gamificationData.streaks.glucose_log_streak} days</strong></p>
        <p>Total Meals Logged: <strong>{gamificationData.meal_counts.total_meals_logged}</strong></p>
      </div>

      <div className="earned-achievements-section">
        <h3>Earned Badges</h3>
        {gamificationData.earned_achievements.length === 0 ? (
          <p>You haven't earned any badges yet. Keep up the good work!</p>
        ) : (
          <div className="achievement-badges">
            {gamificationData.earned_achievements.map((achId) => {
              return (
                <div key={achId} className="achievement-badge earned">
                  <h4>{achievementNames[achId] || achId}</h4>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="coming-soon-achievements-section">
        <h3>Locked Achievements (Progress)</h3>
        {Object.keys(gamificationData.achievements_progress).length === 0 ? (
          <p>No locked achievements currently tracked.</p>
        ) : (
          <div className="achievement-progress-list">
            {Object.entries(gamificationData.achievements_progress).map(([achId, progress]) => {
              const progressPercent = (progress.current / progress.goal) * 100;
              return (
                <div key={achId} className="achievement-progress-item">
                  <h4>{achievementNames[achId] || achId}</h4>
                  <p>{progress.description}</p>
                  <div className="progress-bar-container">
                    <div className="progress-bar" style={{ width: `${Math.min(100, progressPercent)}%` }}></div>
                    <span className="progress-text">{progress.current} / {progress.goal}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default Achievements;
