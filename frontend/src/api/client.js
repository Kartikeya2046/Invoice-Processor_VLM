const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY;

if (!API_KEY) {
  console.warn("VITE_API_KEY is not set in environment variables");
}

async function fetchWithAuth(endpoint, options = {}) {
  const headers = {
    'X-API-Key': API_KEY,
    ...options.headers
  };

  const url = `${BASE_URL}${endpoint}`;
  
  let response;
  try {
    response = await fetch(url, { ...options, headers });
  } catch (error) {
    throw new Error(`Cannot reach the API at ${BASE_URL} — is the backend running? (${error.message})`);
  }

  if (response.status === 403) {
    throw new Error('Invalid or missing API key');
  }

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'No response body');
    throw new Error(`API Error ${response.status}: ${errorText}`);
  }

  return response.json();
}

export async function uploadDocument(file, callbackUrl = null) {
  const formData = new FormData();
  formData.append('file', file);
  if (callbackUrl) {
    formData.append('callback_url', callbackUrl);
  }

  return fetchWithAuth('/documents', {
    method: 'POST',
    // Do not set Content-Type header when sending FormData, fetch will set it automatically with the boundary
    body: formData,
  });
}

export async function getDocumentStatus(documentId) {
  return fetchWithAuth(`/documents/${documentId}/status`);
}

export async function getDocumentDetail(documentId) {
  return fetchWithAuth(`/documents/${documentId}`);
}

export async function listDocuments({ limit = 20, offset = 0, status, documentType } = {}) {
  const params = new URLSearchParams({ limit, offset });
  if (status) params.append('status', status);
  if (documentType) params.append('document_type', documentType);
  
  return fetchWithAuth(`/documents?${params.toString()}`);
}

export async function getReviewQueue({ docType, dateFrom, dateTo, status = 'completed', limit = 20, offset = 0 } = {}) {
  const params = new URLSearchParams({ status, limit, offset });
  if (docType) params.append('doc_type', docType);
  if (dateFrom) params.append('date_from', dateFrom);
  if (dateTo) params.append('date_to', dateTo);
  
  return fetchWithAuth(`/documents/review?${params.toString()}`);
}
