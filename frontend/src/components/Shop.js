import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api';

const defaultDraft = {
  item_id: '',
  quantity: 1,
  notes: '',
};

export const hasInvalidRequestQuantity = (quantity) => {
  const value = Number(quantity);
  return !Number.isInteger(value) || value < 1 || value > 99;
};

const Shop = ({ currentUser }) => {
  const userId = currentUser.id;
  const [catalog, setCatalog] = useState([]);
  const [requests, setRequests] = useState([]);
  const [draft, setDraft] = useState(defaultDraft);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const loadShop = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [catalogData, requestData] = await Promise.all([
        api.get('/api/shop/catalog'),
        api.get(`/api/shop/requests/${userId}`),
      ]);
      setCatalog(catalogData);
      setRequests(requestData);
      setDraft((currentDraft) => {
        if (currentDraft.item_id && catalogData.some((item) => item.id === currentDraft.item_id)) {
          return currentDraft;
        }
        return {
          ...currentDraft,
          item_id: catalogData[0]?.id || '',
        };
      });
    } catch (err) {
      setError(err.message || 'Unable to load shop.');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    loadShop();
  }, [loadShop]);

  const selectedItem = useMemo(
    () => catalog.find((item) => item.id === draft.item_id) || catalog[0] || null,
    [catalog, draft.item_id],
  );

  const saveRequest = async (itemId = draft.item_id) => {
    if (!itemId) return;
    if (hasInvalidRequestQuantity(draft.quantity)) {
      setError('Quantity must be a whole number from 1 to 99.');
      return;
    }
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const result = await api.post(`/api/shop/requests/${userId}`, {
        item_id: itemId,
        quantity: Number(draft.quantity || 1),
        notes: draft.notes,
      });
      setRequests((currentRequests) => {
        const filtered = currentRequests.filter((request) => request.id !== result.request.id);
        return [result.request, ...filtered];
      });
      setDraft((currentDraft) => ({ ...currentDraft, notes: '' }));
      setSuccess('Saved to your request list.');
    } catch (err) {
      setError(err.message || 'Unable to save request.');
    } finally {
      setSaving(false);
    }
  };

  const deleteRequest = async (requestId) => {
    setError('');
    try {
      await api.delete(`/api/shop/request/${requestId}`);
      setRequests((currentRequests) => currentRequests.filter((request) => request.id !== requestId));
    } catch (err) {
      setError(err.message || 'Unable to remove request.');
    }
  };

  if (loading) {
    return <div className="page-panel loading-state" role="status"><p>Loading shop...</p><div className="spinner"></div></div>;
  }

  return (
    <div className="page-panel shop-page">
      <div className="page-header">
        <div>
          <h2>Shop</h2>
          <p>Browse care items and save a request list for supplies you want to revisit later.</p>
        </div>
        <button type="button" onClick={loadShop}>Refresh</button>
      </div>

      <div className="info-banner" role="status">
        This is a lightweight request list, not checkout. Saved items stay local to your account.
      </div>

      {error && <p className="error-message" role="alert">{error}</p>}
      {success && <p className="success-message" role="status">{success}</p>}

      <section className="data-section">
        <h3>Request Builder</h3>
        <div className="form-grid">
          <label>
            Item
            <select value={draft.item_id} onChange={(e) => setDraft({ ...draft, item_id: e.target.value })}>
              {catalog.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </label>
          <label>
            Quantity
            <input type="number" min="1" value={draft.quantity} onChange={(e) => setDraft({ ...draft, quantity: e.target.value })} />
          </label>
          <label className="full-width">
            Notes
            <textarea value={draft.notes} onChange={(e) => setDraft({ ...draft, notes: e.target.value })} placeholder="Optional supply note" />
          </label>
        </div>
        <div className="row-actions">
          <button type="button" onClick={() => saveRequest()} disabled={saving || !draft.item_id}>{saving ? 'Saving...' : 'Save Request'}</button>
          {selectedItem && (
            <button type="button" className="btn-moderate" onClick={() => saveRequest(selectedItem.id)} disabled={saving}>
              Save {selectedItem.name}
            </button>
          )}
        </div>
      </section>

      <section className="data-section">
        <h3>Catalog</h3>
        <div className="catalog-grid">
          {catalog.map((item) => (
            <article className="catalog-card" key={item.id}>
              <div>
                <p className="catalog-category">{item.category}</p>
                <h4>{item.name}</h4>
                <p>{item.description}</p>
              </div>
              <div className="catalog-footer">
                <strong>${item.price.toFixed(2)}</strong>
                <button type="button" className="btn-moderate" onClick={() => {
                  setDraft((currentDraft) => ({ ...currentDraft, item_id: item.id }));
                  saveRequest(item.id);
                }}>
                  Quick Save
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="data-section">
        <h3>Saved Requests</h3>
        {requests.length === 0 ? (
          <p className="muted" role="status">No saved requests yet.</p>
        ) : (
          <div className="item-list">
            {requests.map((request) => (
              <article className="list-item" key={request.id}>
                <div>
                  <h4>{request.item?.name || request.item_name}</h4>
                  <p>{request.quantity} x ${Number(request.item?.price || request.item_price || 0).toFixed(2)}</p>
                  {request.notes && <p>{request.notes}</p>}
                  <p>Status: {request.status}</p>
                </div>
                <button type="button" className="btn-delete" onClick={() => deleteRequest(request.id)}>Delete</button>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
};

export default Shop;
