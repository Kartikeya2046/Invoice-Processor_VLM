import React, { useState } from 'react';
import UploadZone from '../components/UploadZone';
import DocumentList from '../components/DocumentList';
import DocumentDetail from '../components/DocumentDetail';

export default function Dashboard() {
  const [selectedDocumentId, setSelectedDocumentId] = useState(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleUploadSuccess = () => {
    setRefreshTrigger(prev => prev + 1);
  };

  const handleSelectDocument = (id) => {
    setSelectedDocumentId(id);
  };

  return (
    <div className="dashboard-container">
      <div className="sidebar">
        <UploadZone onUploadSuccess={handleUploadSuccess} />
        <DocumentList 
          refreshTrigger={refreshTrigger} 
          onSelectDocument={handleSelectDocument}
          selectedDocumentId={selectedDocumentId}
        />
      </div>
      <div className="main-panel">
        <DocumentDetail documentId={selectedDocumentId} />
      </div>
    </div>
  );
}
