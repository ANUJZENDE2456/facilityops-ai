const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1';

async function request(path, { params = {}, method = 'GET', body } = {}) {
  const query = new URLSearchParams(params).toString();
  const response = await fetch(`${API_BASE_URL}/energy/${path}${query ? `?${query}` : ''}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`Request failed (${path}): ${response.status}`);
  return response.json();
}

export const getFacilities = () => request('facilities');
export const getCampus = () => request('campus');
export const getSummary = (facility_id, days) => request('summary', { params: { facility_id, days } });
export const getTimeseries = (facility_id, meter_id, hours) => request('timeseries', { params: { facility_id, meter_id, hours } });
export const getAnomalies = (facility_id, hours = 168) => request('anomalies', { params: { facility_id, hours } });
export const askAgent = (facility_id, question) => request('ask', { method: 'POST', body: { facility_id, question } });
