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

export interface DownloadResponse {
    doc_id: string;
    url: string; // The primary download link
    download_url?: string; // Alias
    method?: string; // 'webview', 'export_pdf', 'drive_direct', etc.
    filename?: string;
    mime_type?: string;
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
    updateDocStatus: async (docId: string, status: 'APPROVED' | 'REJECTED', reason?: string): Promise<any> => {
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

    // 3. Get Secure Download URL (Legacy)
    getDownloadUrl: async (docId: string): Promise<DownloadResponse> => {
        const res = await fetch(`${API_BASE_URL}/api/docs/${docId}/download`, {
            headers: getHeaders()
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Failed to get download link");
        }
        return await res.json();
    },

    // 4. Download Document (Streaming Support)
    downloadDocument: async (docId: string): Promise<any> => {
        const res = await fetch(`${API_BASE_URL}/api/docs/${docId}/download`, {
            headers: getHeaders()
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || `Download failed: ${res.status}`);
        }

        const contentType = res.headers.get("content-type") || "";

        // A. JSON Response (Fallback)
        if (contentType.includes("application/json")) {
            return await res.json();
        }

        // B. Blob Response (Streaming)
        const blob = await res.blob();

        // Extract Filename from Content-Disposition
        const disposition = res.headers.get('Content-Disposition');
        let filename = 'document.pdf';
        if (disposition && disposition.indexOf('filename=') !== -1) {
            const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
            if (matches != null && matches[1]) {
                filename = matches[1].replace(/['"]/g, '');
            }
        }

        return { blob, filename, contentType };
    }
};
