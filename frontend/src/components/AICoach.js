import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

const AICoach = ({ currentUser }) => {
  const navigate = useNavigate();
  const [message, setMessage] = useState('');
  const [chat, setChat] = useState([
    { role: 'coach', text: 'I can reflect on your saved logs, highlight safety reminders, and help prepare doctor questions. I cannot recommend insulin doses.' },
  ]);
  const [nextTop5, setNextTop5] = useState([]);
  const [loading, setLoading] = useState(false);

  const sendMessage = async (event) => {
    event.preventDefault();
    if (!message.trim()) return;
    const userText = message.trim();
    setChat((items) => [...items, { role: 'user', text: userText }]);
    setMessage('');
    setLoading(true);
    try {
      const result = await api.post('/api/coach/respond', { user_id: currentUser.id, message: userText });
      setChat((items) => [...items, { role: 'coach', text: result.reply || result.message }]);
      setNextTop5(Array.isArray(result.next_top_5) ? result.next_top_5 : []);
    } catch (err) {
      setChat((items) => [...items, { role: 'coach', text: err.message || 'I cannot answer that safely. Please contact your care team.' }]);
      setNextTop5([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="ai-coach-container">
      <div className="page-header">
        <div>
          <h2>Coach</h2>
          <p>AI-assisted reflection and safety support based on your saved logs.</p>
        </div>
        <button type="button" onClick={() => navigate('/emergency')}>Emergency Guidance</button>
      </div>

      <div className="info-banner" role="status">
        This coach uses an external AI service. Do not include names or other identifying details. It cannot prescribe insulin, override clinician advice, or replace emergency care.
      </div>

      <div className="chat-panel">
        {chat.map((entry, index) => (
          <div className={`chat-message ${entry.role}`} key={`${entry.role}-${index}`}>
            <strong>{entry.role === 'coach' ? 'Coach' : 'You'}</strong>
            <p>{entry.text}</p>
          </div>
        ))}
        {loading && <p className="muted" role="status" aria-live="polite">Thinking...</p>}
      </div>

      {nextTop5.length > 0 && (
        <div className="info-banner" role="status" aria-live="polite">
          <strong>Next top 5</strong>
          <ol>
            {nextTop5.map((item) => <li key={item}>{item}</li>)}
          </ol>
        </div>
      )}

      <form className="chat-form" onSubmit={sendMessage}>
        <label htmlFor="coach-message" className="sr-only">Message for coach</label>
        <input id="coach-message" value={message} maxLength={1000} onChange={(e) => setMessage(e.target.value)} placeholder="Ask about patterns or doctor questions..." aria-label="Message for coach" required />
        <button type="submit" disabled={loading || !message.trim()} aria-label="Send message">Send</button>
      </form>
    </div>
  );
};

export default AICoach;
