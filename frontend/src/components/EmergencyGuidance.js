import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

const emptyContact = { id: '', name: '', phone: '', relationship: '' };

export const hasIncompleteContact = (contacts) => contacts.some((contact) => (
  Boolean((contact.name || '').trim()) !== Boolean((contact.phone || '').trim())
));

const EmergencyGuidance = ({ currentUser }) => {
  const [guidance, setGuidance] = useState(null);
  const [contacts, setContacts] = useState([emptyContact]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const userId = currentUser.id;

  const loadGuidance = useCallback(async () => {
    setError('');
    setSuccess('');
    setLoading(true);
    try {
      const [guidanceData, contactData] = await Promise.all([
        api.get('/api/emergency/guidance'),
        api.get(`/api/emergency/contacts/${userId}`),
      ]);
      setGuidance(guidanceData);
      setContacts(contactData.length > 0 ? contactData : [emptyContact]);
    } catch (err) {
      setError(err.message || 'Unable to load emergency guidance.');
      setContacts([emptyContact]);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    loadGuidance();
  }, [loadGuidance]);

  const updateContact = (index, key, value) => {
    setContacts(contacts.map((contact, contactIndex) => (
      contactIndex === index ? { ...contact, [key]: value } : contact
    )));
  };

  const addContact = () => {
    setContacts([...contacts, { ...emptyContact }]);
  };

  const removeContact = (index) => {
    const nextContacts = contacts.filter((_, contactIndex) => contactIndex !== index);
    setContacts(nextContacts.length > 0 ? nextContacts : [{ ...emptyContact }]);
  };

  const saveContacts = async () => {
    if (hasIncompleteContact(contacts)) {
      setError('Each emergency contact needs both a name and phone number.');
      setSuccess('');
      return;
    }
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const result = await api.put(`/api/emergency/contacts/${userId}`, {
        contacts,
      });
      setContacts(result.contacts.length > 0 ? result.contacts : [{ ...emptyContact }]);
      setSuccess('Emergency contacts saved.');
    } catch (err) {
      setError(err.message || 'Unable to save emergency contacts.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="emergency-guidance-container loading-state" role="status"><p>Loading emergency guidance...</p><div className="spinner"></div></div>;
  }

  return (
    <div className="emergency-guidance-container">
      <div className="page-header">
        <div>
          <h2>Emergency Guidance</h2>
          <p>Clear protocols for severe low or high glucose situations.</p>
        </div>
        <button className="btn-delete" type="button" onClick={() => window.location.assign('tel:911')}>Call Emergency Services</button>
      </div>

      {error && <p className="error-message" role="alert">{error}</p>}
      {success && <p className="success-message" role="status">{success}</p>}
      <div className="emergency-banner" role="status">
        <h3>Not a substitute for emergency care</h3>
        <p>{guidance?.disclaimer || 'If symptoms are severe, contact emergency services immediately.'}</p>
      </div>

      <section className="data-section">
        <h3>Severe Low / High Protocols</h3>
        <div className="item-list">
          {(guidance?.protocols || []).map((item) => <article className="list-item" key={item}><p>{item}</p></article>)}
          <article className="list-item"><p>Do not use this page for dosing decisions. Follow your clinician’s plan.</p></article>
        </div>
      </section>

      <section className="data-section">
        <h3>Caregiver Contacts</h3>
        {contacts.map((contact, index) => (
          <div className="contact-card" key={contact.id || index}>
            <div className="form-grid">
              <label>Name<input value={contact.name || ''} onChange={(e) => updateContact(index, 'name', e.target.value)} /></label>
              <label>Phone<input type="tel" value={contact.phone || ''} onChange={(e) => updateContact(index, 'phone', e.target.value)} /></label>
              <label>Relationship<input value={contact.relationship || ''} onChange={(e) => updateContact(index, 'relationship', e.target.value)} /></label>
            </div>
            <div className="row-actions">
              <button type="button" className="btn-delete" onClick={() => removeContact(index)}>Remove</button>
            </div>
          </div>
        ))}
        <div className="row-actions">
          <button type="button" className="btn-moderate" onClick={addContact}>Add Another Contact</button>
          <button type="button" onClick={saveContacts} disabled={saving}>{saving ? 'Saving...' : 'Save Contacts'}</button>
        </div>
      </section>
    </div>
  );
};

export default EmergencyGuidance;
