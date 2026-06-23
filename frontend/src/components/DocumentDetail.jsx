import React, { useEffect, useState } from 'react';
import { getDocumentDetail } from '../api/client';
import StatusBadge from './StatusBadge';

const formatFieldName = (name) => {
  if (!name) return '';
  return name.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
};

export default function DocumentDetail({ documentId }) {
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  useEffect(() => {
    if (!documentId) return;

    let isMounted = true;

    const fetchDetail = async () => {
      setLoading(true);
      setErrorMsg(null);
      try {
        const data = await getDocumentDetail(documentId);
        if (isMounted) setDoc(data);
      } catch (err) {
        if (isMounted) setErrorMsg(err.message);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchDetail();

    return () => {
      isMounted = false;
    };
  }, [documentId]);

  if (!documentId) {
    return <div className="document-detail empty-state">Select a document to view details</div>;
  }

  if (loading) {
    return <div className="document-detail loading-state">Loading document details...</div>;
  }

  if (errorMsg) {
    return (
      <div className="document-detail">
        <div className="error-banner">{errorMsg}</div>
      </div>
    );
  }

  if (!doc) {
    return null;
  }

  const { status, failed_stage, failure_reason, extraction_result, file_name, document_type, created_at } = doc;

  return (
    <div className="document-detail">
      <div className="detail-header">
        <h2>{file_name}</h2>
        <div className="meta-tags">
          <StatusBadge status={status} />
          {document_type && <span className="tag type-tag">{document_type}</span>}
          <span className="tag date-tag">{new Date(created_at).toLocaleString()}</span>
        </div>
      </div>

      {['pending', 'extracting', 'validating'].includes(status) && (
        <div className="processing-state">
          <div className="spinner"></div>
          <h3>Processing Document</h3>
          <p>Current stage: <strong>{status}</strong></p>
          <p className="note">Note: SLM validation alone can take 30-140 seconds.</p>
        </div>
      )}

      {status === 'failed' && (
        <div className="failed-state error-banner">
          <h3>Extraction Failed</h3>
          <p><strong>Failed Stage:</strong> {failed_stage || 'Unknown'}</p>
          <p><strong>Reason:</strong> {failure_reason || 'No reason provided'}</p>
        </div>
      )}

      {status === 'completed' && extraction_result && (
        <div className="completed-state">
          <div className="summary-cards">
            <div className="card">
              <h4>Overall Confidence</h4>
              <div className="score">{(extraction_result.overall_confidence * 100).toFixed(1)}%</div>
            </div>
            {extraction_result.requires_review && (
              <div className="card alert-card">
                <h4>Manual Review Required</h4>
                <p>Some fields have low confidence or failed validation.</p>
              </div>
            )}
          </div>

          <div className="fields-table-container">
            <h3>Extracted Fields</h3>
            <table className="fields-table">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Value</th>
                  <th>Confidence</th>
                  <th>Flags</th>
                </tr>
              </thead>
              <tbody>
                {extraction_result.fields.map((field, idx) => (
                  <tr key={idx} className={field.flag ? 'flagged-row' : ''}>
                    <td>{formatFieldName(field.field_name)}</td>
                    <td>{field.value}</td>
                    <td>{field.confidence !== null ? `${(field.confidence * 100).toFixed(1)}%` : '—'}</td>
                    <td>{field.flag || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
