import React, { useEffect, useState, useRef } from 'react';
import { listDocuments, getDocumentStatus } from '../api/client';
import StatusBadge from './StatusBadge';

export default function DocumentList({ refreshTrigger, onSelectDocument, selectedDocumentId }) {
  const [documents, setDocuments] = useState([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState(null);
  const limit = 20;

  const pollingRefs = useRef({});

  const fetchDocuments = async (currentOffset = 0, append = false) => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const data = await listDocuments({ limit, offset: currentOffset });
      setTotal(data.total);
      if (append) {
        setDocuments(prev => {
          const newDocs = data.items.filter(item => !prev.some(p => p.document_id === item.document_id));
          return [...prev, ...newDocs];
        });
      } else {
        setDocuments(data.items);
      }
    } catch (err) {
      setErrorMsg(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments(0, false);
    setOffset(0);
    // Cleanup all intervals on unmount
    return () => {
      Object.values(pollingRefs.current).forEach(clearInterval);
    };
  }, [refreshTrigger]);

  const loadMore = () => {
    const newOffset = offset + limit;
    setOffset(newOffset);
    fetchDocuments(newOffset, true);
  };

  const handleDocumentUpdate = (docId, updatedData) => {
    setDocuments(prev => prev.map(doc => {
      if (doc.document_id === docId) {
        return { ...doc, ...updatedData };
      }
      return doc;
    }));
  };

  useEffect(() => {
    documents.forEach(doc => {
      if (['pending', 'extracting', 'validating'].includes(doc.status)) {
        if (!pollingRefs.current[doc.document_id]) {
          pollingRefs.current[doc.document_id] = setInterval(async () => {
            try {
              const statusData = await getDocumentStatus(doc.document_id);
              if (['completed', 'failed'].includes(statusData.status)) {
                clearInterval(pollingRefs.current[doc.document_id]);
                delete pollingRefs.current[doc.document_id];
                // Refresh the whole list or just this doc?
                // For simplicity, just fetch documents list again to get extraction info if completed,
                // or update just this doc and missing extraction info.
                // It's safer to refresh list to get confidence score.
                fetchDocuments(0, false);
              } else {
                handleDocumentUpdate(doc.document_id, { status: statusData.status });
              }
            } catch (err) {
              console.error('Polling error:', err);
              // don't interrupt UI for polling errors, just stop polling if not found
              if (err.message.includes('404')) {
                clearInterval(pollingRefs.current[doc.document_id]);
                delete pollingRefs.current[doc.document_id];
              }
            }
          }, 5000);
        }
      } else {
        if (pollingRefs.current[doc.document_id]) {
          clearInterval(pollingRefs.current[doc.document_id]);
          delete pollingRefs.current[doc.document_id];
        }
      }
    });
  }, [documents]);

  const formatConfidence = (conf) => {
    if (conf === null || conf === undefined) return '—';
    return `${(conf * 100).toFixed(1)}%`;
  };

  return (
    <div className="document-list">
      <h3>Documents</h3>
      {errorMsg && <div className="error-banner">{errorMsg}</div>}
      
      <div className="list-container">
        {documents.map(doc => (
          <div 
            key={doc.document_id} 
            className={`document-row ${selectedDocumentId === doc.document_id ? 'selected' : ''}`}
            onClick={() => onSelectDocument(doc.document_id)}
          >
            <div className="doc-info">
              <div className="doc-filename">{doc.file_name}</div>
              <div className="doc-meta">
                <span className="doc-type">{doc.document_type || 'Unknown'}</span>
                <span className="doc-confidence">Score: {formatConfidence(doc.overall_confidence)}</span>
              </div>
            </div>
            <StatusBadge status={doc.status} />
          </div>
        ))}
        
        {documents.length === 0 && !loading && !errorMsg && (
          <div className="empty-state">No documents found</div>
        )}

        {loading && <div className="loading-indicator">Loading...</div>}

        {documents.length < total && (
          <button className="btn load-more-btn" onClick={loadMore} disabled={loading}>
            {loading ? 'Loading...' : 'Load More'}
          </button>
        )}
      </div>
    </div>
  );
}
