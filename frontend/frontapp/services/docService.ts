// import { API_BASE_URL } from './dataService';
import { DocCard } from '../types';

// Helper to get API Base URL (Self-contained to avoid circular deps)
const getBaseUrl = () => {
    // 1. Local Development 
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        return 'http://localhost:8000';
    }
    // 2. Production
    return 'https://omnihub-backend-707724932002.asia-northeast3.run.app';
};
const API_BASE_URL = getBaseUrl();

// Helper to get headers with Auth Token
const getHeaders = () => {
    const token = localStorage.getItem('omnihub_token');
    return {
        'Authorization': token ? `Bearer ${token}` : ''
    };
};


export interface DocDetail extends DocCard {
    folder_path?: string;
    modified_time?: string;
    source_link?: string;
    review_status?: string;
    card?: {
        l1?: string;
        l2?: string;
        l3?: string;
    };
    policy?: {
        security_level?: string;
        ssot_level?: string;
    };
    concepts?: any[];
    evidence?: any[];
}

export const DocService = {
    // 1. Get Document Details
    getDocDetail: async (docId: string): Promise<DocDetail> => {
        const res = await fetch(`${API_BASE_URL}/api/docs/${docId}`, {
            headers: getHeaders()
        });
        if (!res.ok) throw new Error("Failed to fetch document details");
        return await res.json();
    },

    // 2. Update Document Status (Approve/Reject)
    updateDocStatus: async (docId: string, status: 'approved' | 'rejected', reason?: string): Promise<any> => {
        const res = await fetch(`${API_BASE_URL}/api/docs/${docId}/status`, {
            method: 'PATCH',
            headers: {
                ...getHeaders(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ status, reason })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Failed to update status");
        }
        return await res.json();
    },

    // 3. Get Secure Download URL
    getDownloadUrl: async (docId: string): Promise<string> => {
        const res = await fetch(`${API_BASE_URL}/api/docs/${docId}/download`, {
            headers: getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Failed to get download link");
        }
        const data = await res.json();
        return data.url;
    }
};
