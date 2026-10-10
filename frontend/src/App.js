import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import LogMeal from './components/LogMeal';
import AICoach from './components/AICoach';
import EmergencyGuidance from './components/EmergencyGuidance';
import NotificationSettings from './components/NotificationSettings';
import Analytics from './components/Analytics';
import Achievements from './components/Achievements';
import CommunityForum from './components/CommunityForum';
import MealHistory from './components/MealHistory';
import InsulinLog from './components/InsulinLog';
import Shop from './components/Shop';
import CGMSettings from './components/CGMSettings';
import { api, apiRequest, clearApiFailureTrace } from './api';

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="dashboard-container error-state">
          <h2>Something went wrong</h2>
          <p className="error-message">The app hit an unexpected error. Please refresh or sign in again.</p>
        </div>
      );
    }
    return this.props.children;
  }
}

function ApiFailureBanner() {
  const [failure, setFailure] = useState(null);

  useEffect(() => {
    if (process.env.NODE_ENV === 'production') return undefined;
    const handler = (event) => {
      setFailure(event.detail || null);
    };
    const clearHandler = () => setFailure(null);
    window.addEventListener('gluverse-api-failure', handler);
    window.addEventListener('gluverse-api-failure-clear', clearHandler);
    window.addEventListener('gluverse-auth-expired', clearHandler);
    return () => {
      window.removeEventListener('gluverse-api-failure', handler);
      window.removeEventListener('gluverse-api-failure-clear', clearHandler);
      window.removeEventListener('gluverse-auth-expired', clearHandler);
    };
  }, []);

  if (process.env.NODE_ENV === 'production' || !failure) return null;

  return (
    <div className="info-banner" style={{ margin: '0 0 16px 0' }}>
      <strong>Request trace:</strong> {failure.method} {failure.path} returned {failure.status} ({failure.category})
      <div>{failure.message}</div>
    </div>
  );
}

function LoginScreen({ onLogin }) {
  const [form, setForm] = useState({ username: '', password: '' });
  const [mode, setMode] = useState('login');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    try {
      const path = mode === 'login' ? '/api/auth/login' : '/api/auth/register';
      const result = await api.post(path, form);
      clearApiFailureTrace();
      onLogin(result.user);
    } catch (err) {
      setError(err.message || 'Authentication failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-panel">
        <h1>GluVerse</h1>
        <p>Sign in to your diabetes companion workspace.</p>
        <form onSubmit={submit} className="form-card">
          <label>Username<input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></label>
          <label>Password<input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
          {error && <p className="error-message">{error}</p>}
          <button type="submit" disabled={loading}>{loading ? 'Working...' : mode === 'login' ? 'Sign In' : 'Create Account'}</button>
        </form>
        <div className="segmented-control">
          <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>Sign In Mode</button>
          <button type="button" className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')}>Create Account Mode</button>
        </div>
      </div>
    </div>
  );
}

function ProtectedRoute({ currentUser, children }) {
  const location = useLocation();
  if (!currentUser) {
    return <Navigate to="/" replace state={{ from: location }} />;
  }
  return children;
}

function ProtectedLayout({ currentUser, onLogout }) {
  return (
    <ProtectedRoute currentUser={currentUser}>
      <div className="app-layout">
        <Sidebar currentUser={currentUser} onLogout={onLogout} />
        <div className="main-content">
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard currentUser={currentUser} />} />
            <Route path="/log-meal" element={<LogMeal currentUser={currentUser} />} />
            <Route path="/meal-history" element={<MealHistory currentUser={currentUser} />} />
            <Route path="/insulin" element={<InsulinLog currentUser={currentUser} />} />
            <Route path="/ai-coach" element={<AICoach currentUser={currentUser} />} />
            <Route path="/emergency" element={<EmergencyGuidance currentUser={currentUser} />} />
            <Route path="/settings/notifications" element={<NotificationSettings currentUser={currentUser} />} />
            <Route path="/analytics" element={<Analytics userId={currentUser.id} />} />
            <Route path="/achievements" element={<Achievements userId={currentUser.id} />} />
            <Route path="/community" element={<CommunityForum currentUser={currentUser} isAdmin={currentUser.id === 'admin123'} />} />
            <Route path="/shop" element={<Shop currentUser={currentUser} />} />
            <Route path="/settings/cgm" element={<CGMSettings />} />
          </Routes>
        </div>
      </div>
    </ProtectedRoute>
  );
}

function AppShell({ currentUser, onLogout }) {
  return <ProtectedLayout currentUser={currentUser} onLogout={onLogout} />;
}

function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [loadingAuth, setLoadingAuth] = useState(true);

  useEffect(() => {
    const loadUser = async () => {
      try {
        const response = await apiRequest('/api/auth/me');
        clearApiFailureTrace();
        setCurrentUser(response.user);
      } catch {
        setCurrentUser(null);
      } finally {
        setLoadingAuth(false);
      }
    };
    loadUser();
  }, []);

  useEffect(() => {
    const handleExpired = () => {
      setCurrentUser(null);
      setLoadingAuth(false);
    };
    window.addEventListener('gluverse-auth-expired', handleExpired);
    return () => window.removeEventListener('gluverse-auth-expired', handleExpired);
  }, []);

  const handleLogin = (user) => {
    clearApiFailureTrace();
    setCurrentUser(user);
    setLoadingAuth(false);
  };

  const handleLogout = async () => {
    try {
      await api.post('/api/auth/logout', {});
    } catch {
      // ignore logout failures locally
    } finally {
      clearApiFailureTrace();
      setCurrentUser(null);
    }
  };

  if (!currentUser) {
    if (loadingAuth) {
      return <div><ApiFailureBanner /><div className="dashboard-container loading-state"><p>Loading session...</p><div className="spinner"></div></div></div>;
    }
    return <div><ApiFailureBanner /><LoginScreen onLogin={handleLogin} /></div>;
  }

  return <AppErrorBoundary><ApiFailureBanner /><Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><AppShell currentUser={currentUser} onLogout={handleLogout} /></Router></AppErrorBoundary>;
}

export { AppErrorBoundary, LoginScreen, ProtectedRoute };
export default App;
