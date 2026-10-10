import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api';

const CommunityForum = ({ currentUser, isAdmin }) => {
  const [posts, setPosts] = useState([]);
  const [newPostContent, setNewPostContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [postError, setPostError] = useState(null);
  const [notice, setNotice] = useState('');

  const loadPosts = useCallback(async () => {
    try {
      const fetchedPosts = await api.get('/api/community/posts');
      setPosts(fetchedPosts);
    } catch (err) {
      console.error('Failed to load community posts:', err);
      setError('Failed to load community posts. Please try again later.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPosts();
  }, [loadPosts]);

  const handleSubmitNewPost = async (e) => {
    e.preventDefault();
    setPostError(null);
    if (!newPostContent.trim()) {
      setPostError('Post content cannot be empty.');
      return;
    }

    try {
      const result = await api.post('/api/community/posts', {
        content: newPostContent,
      });
      if (result.success) {
        setPosts((prev) => [{ ...result.post, username: currentUser.username, display_content: result.post.content }, ...prev]);
        setNewPostContent('');
      } else {
        setPostError(result.message);
      }
    } catch (err) {
      console.error('Error creating post:', err);
      setPostError('Failed to create post. Please try again.');
    }
  };

  const handleReportPost = async (postId) => {
    setNotice('');
    try {
      const result = await api.post(`/api/community/posts/${postId}/report`, {
        reporter_id: currentUser.id,
        reason: 'User reported as unsafe or off-topic.',
      });
      setNotice(result.message || 'Report saved.');
    } catch (err) {
      console.error('Error reporting post:', err);
      setNotice('Unable to report post right now.');
    }
  };

  const handleHidePost = async (postId) => {
    if (!window.confirm('Are you sure you want to hide this post?')) return;
    try {
      await api.post(`/api/community/posts/${postId}/hide`, {});
      setPosts(posts.map(p => p.id === postId ? { ...p, status: 'hidden' } : p));
    } catch (err) {
      console.error('Error hiding post:', err);
      setNotice('Failed to hide post.');
    }
  };

  const handleDeletePost = async (postId) => {
    if (!window.confirm('Are you sure you want to permanently delete this post? This cannot be undone.')) return;
    try {
      await api.delete(`/api/community/posts/${postId}`);
      setPosts(posts.filter(p => p.id !== postId));
    } catch (err) {
      console.error('Error deleting post:', err);
      setNotice('Failed to delete post.');
    }
  };

  if (loading) return <p role="status">Loading community forum...</p>;
  if (error) return <p className="error-message" role="alert">Error loading forum: {error}</p>;

  return (
    <div className="community-forum-container">
      <h2>Community Forum</h2>
      <p className="info-banner" role="status">Community posts are peer support, not medical advice. Suspicious test/script content is blocked before posting.</p>
      {notice && <p className="success-message" role="status">{notice}</p>}

      <form onSubmit={handleSubmitNewPost} className="new-post-form">
        <textarea
          aria-label="New community post"
          value={newPostContent}
          onChange={(e) => setNewPostContent(e.target.value)}
          placeholder="Share your thoughts or ask a question..."
          rows="4"
        />
        {postError && <p className="error-message" role="alert">{postError}</p>}
        <button type="submit" disabled={!newPostContent.trim()}>Post</button>
      </form>

      <div className="posts-list">
        {posts.length === 0 ? (
          <p role="status">No posts yet. Be the first to share!</p>
        ) : (
          posts.map((post) => (
            <div key={post.id} className={`community-post ${post.status === 'hidden' ? 'hidden-post' : ''}`}>
              <p className="post-meta">
                <strong>{post.username}</strong> on {new Date(post.posted_at).toLocaleString()}
                {post.status === 'hidden' && <span className="status-indicator">(Hidden)</span>}
              </p>
              <p className="post-content">{post.content}</p>
              {isAdmin && post.status !== 'hidden' && (
                <div className="moderation-actions">
                  <button type="button" onClick={() => handleHidePost(post.id)} className="btn-moderate">Hide</button>
                </div>
              )}
              {isAdmin && (
                <div className="moderation-actions">
                  <button type="button" onClick={() => handleDeletePost(post.id)} className="btn-moderate btn-delete">Delete</button>
                </div>
              )}
              {!isAdmin && (
                <div className="moderation-actions">
                  <button type="button" onClick={() => handleReportPost(post.id)} className="btn-moderate">Report</button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default CommunityForum;
