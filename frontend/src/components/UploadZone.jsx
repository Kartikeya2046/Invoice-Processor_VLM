import React, { useRef, useState } from 'react';
import { uploadDocument } from '../api/client';

const ALLOWED_EXTS = ['.png', '.jpg', '.jpeg', '.pdf'];

export default function UploadZone({ onUploadSuccess }) {
  const [isDragging, setIsDragging] = useState(false);
  const [uploadQueue, setUploadQueue] = useState([]);
  const [skippedCount, setSkippedCount] = useState(0);
  const [errorMsg, setErrorMsg] = useState(null);

  const fileInputRef = useRef(null);
  const folderInputRef = useRef(null);

  const processFiles = async (fileList) => {
    setErrorMsg(null);
    setSkippedCount(0);
    
    const validFiles = [];
    let skipped = 0;

    for (let i = 0; i < fileList.length; i++) {
      const file = fileList[i];
      const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
      if (ALLOWED_EXTS.includes(ext)) {
        validFiles.push(file);
      } else {
        skipped++;
      }
    }

    if (skipped > 0) {
      setSkippedCount(skipped);
    }

    if (validFiles.length === 0) {
      if (skipped > 0) {
        setErrorMsg(`Skipped ${skipped} unsupported file(s). No valid files to upload.`);
      }
      return;
    }

    const queueItems = validFiles.map(file => ({
      id: Math.random().toString(36).substr(2, 9),
      file,
      status: 'uploading',
      error: null
    }));

    setUploadQueue(prev => [...prev, ...queueItems]);

    for (const item of queueItems) {
      try {
        const res = await uploadDocument(item.file);
        setUploadQueue(prev => prev.map(q => q.id === item.id ? { ...q, status: 'queued', documentId: res.document_id } : q));
        if (onUploadSuccess) {
          onUploadSuccess();
        }
      } catch (err) {
        setUploadQueue(prev => prev.map(q => q.id === item.id ? { ...q, status: 'error', error: err.message } : q));
        setErrorMsg(err.message);
      }
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files);
      e.target.value = ''; // Reset input
    }
  };

  return (
    <div className="upload-zone-container">
      {errorMsg && <div className="error-banner">{errorMsg}</div>}
      {skippedCount > 0 && <div className="info-banner">Skipped {skippedCount} unsupported file(s).</div>}
      
      <div 
        className={`dropzone ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <p>Drag & Drop files here</p>
        <div className="upload-buttons">
          <button onClick={() => fileInputRef.current?.click()} className="btn">Upload Files</button>
          {/* Note: Firefox support for webkitdirectory is inconsistent */}
          <button onClick={() => folderInputRef.current?.click()} className="btn btn-secondary">Upload Folder</button>
        </div>
      </div>

      <input 
        type="file" 
        multiple 
        accept=".png,.jpg,.jpeg,.pdf" 
        style={{ display: 'none' }} 
        ref={fileInputRef}
        onChange={handleFileChange}
      />
      <input 
        type="file" 
        multiple 
        webkitdirectory="true"
        directory="true"
        style={{ display: 'none' }} 
        ref={folderInputRef}
        onChange={handleFileChange}
      />

      {uploadQueue.length > 0 && (
        <div className="upload-queue">
          <h4>Upload Progress</h4>
          <ul>
            {uploadQueue.map(item => (
              <li key={item.id} className={`queue-item status-${item.status}`}>
                <span className="filename">{item.file.name}</span>
                <span className="status">
                  {item.status === 'uploading' && 'Uploading...'}
                  {item.status === 'queued' && 'Queued'}
                  {item.status === 'error' && `Error: ${item.error}`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
