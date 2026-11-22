
const API_BASE_URL =
    import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1';

async function request(path, { method = 'GET', body } = {}) {
    const response = await fetch(`${API_BASE_URL}/maintenance/${path}`, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
    });

    if (!response.ok) {
        let message = `Request failed: ${response.status}`;

        try {
            const error = await response.json();
            message = error.detail || message;
        } catch {
            // Keep the default error message.
        }

        throw new Error(message);
    }

    return response.json();
}

// Facility analysis
export const analyzeFacility = (facilityId) =>
    request(`facilities/${facilityId}/analyze`);

// Individual asset analysis
export const analyzeAsset = (assetId) =>
    request(`assets/${assetId}/analyze`);

// Work orders
export const getFacilityWorkOrders = (facilityId) =>
    request(`facilities/${facilityId}/work-orders`);

export const getAssetWorkOrders = (assetId) =>
    request(`assets/${assetId}/work-orders`);

export const createWorkOrder = (assetId, data) =>
    request(`assets/${assetId}/work-orders`, {
        method: 'POST',
        body: data,
    });

export const updateWorkOrderStatus = (workOrderId, status) =>
    request(`work-orders/${workOrderId}/status`, {
        method: 'PATCH',
        body: { status },
    });
// Maintenance AI Agent
export const askMaintenanceAgent = (facilityId, question) =>
    request(`facilities/${facilityId}/ask`, {
        method: 'POST',
        body: { question },
    });