import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';

const Sidebar = ({ onLogout }) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const navItems = [
    { name: 'Dashboard', path: '/dashboard' },
    { name: 'Log Meal', path: '/log-meal' },
    { name: 'Meal History', path: '/meal-history' },
    { name: 'Insulin', path: '/insulin' },
    { name: 'Coach', path: '/ai-coach' },
    { name: 'Emergency', path: '/emergency' },
    { name: 'Analytics', path: '/analytics' },
    { name: 'Achievements', path: '/achievements' },
    { name: 'Community', path: '/community' },
    { name: 'Alerts', path: '/settings/notifications' },
    { name: 'CGM', path: '/settings/cgm' },
    { name: 'Shop', path: '/shop', alwaysVisible: true },
  ];

  return (
    <nav className="sidebar">
      <div className="sidebar-header">
        <h3>GluVerse</h3>
      </div>
      <button
        type="button"
        className="btn-moderate sidebar-menu-toggle"
        aria-expanded={menuOpen}
        aria-controls="sidebar-navigation"
        onClick={() => setMenuOpen(!menuOpen)}
      >
        Menu
      </button>
      <ul id="sidebar-navigation" className={`sidebar-nav ${menuOpen ? 'is-open' : ''}`}>
        {navItems.map((item) => (
          <li key={item.name} className={`nav-item ${item.alwaysVisible ? 'always-visible-item' : ''}`}>
            <NavLink
              to={item.path}
              className={({ isActive }) => (isActive ? 'active-link' : '')}
              onClick={() => setMenuOpen(false)}
            >
              {item.name}
            </NavLink>
          </li>
        ))}
        {onLogout && (
          <li className="nav-item">
            <button type="button" className="btn-moderate sidebar-button" onClick={onLogout}>Logout</button>
          </li>
        )}
      </ul>
    </nav>
  );
};

export default Sidebar;
