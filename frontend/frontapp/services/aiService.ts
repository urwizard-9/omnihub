import {
    RAGResponse,
    RAGRequest,
    GraphData,
    DocCard,
    TreeResponse
} from '../types';
import { API_BASE_URL } from './dataService';

// Helper to get headers with Auth Token
const getHeaders = () => {
    const token = localStorage.getItem('omnihub_token');
    return {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : ''
    };
};

export const AIService = {
    // 1. RAG Search
    searchRAG: async (query: string, scope?: any): Promise<RAGResponse> => {
        const res = await fetch(`${API_BASE_URL}/api/search/rag`, {
            method: 'POST',
            headers: getHeaders(),
            body: JSON.stringify({ query, scope })
        });
        if (!res.ok) throw new Error("RAG Search failed");
        return await res.json();
    },

    // 2. Graph Ops
    getGraphInit: async (limit: number = 50, mode: 'overview' | 'hybrid' = 'overview'): Promise<GraphData> => {
        const res = await fetch(`${API_BASE_URL}/api/graph/init?limit=${limit}&mode=${mode}`, {
            headers: getHeaders()
        });
        if (!res.ok) throw new Error("Graph Init failed");
        return await res.json();
    },

    expandGraph: async (nodeId: string, nodeType: 'document' | 'concept', docLimit: number = 15): Promise<GraphData> => {
        const res = await fetch(`${API_BASE_URL}/api/graph/expand?node_id=${nodeId}&node_type=${nodeType}&doc_limit=${docLimit}`, {
            headers: getHeaders()
        });
        if (!res.ok) throw new Error("Graph Expand failed");
        return await res.json();
    },

    // 3. Tree Ops
    getTreeStructure: async (folderPath: string = '/'): Promise<TreeResponse> => {
        // Encoding path parameter
        const encodedPath = encodeURIComponent(folderPath);
        const res = await fetch(`${API_BASE_URL}/api/tree?folder=${encodedPath}`, {
            headers: getHeaders()
        });
        if (!res.ok) throw new Error("Fetch Tree failed");
        return await res.json();
    },

    // 4. Doc Card
    getDocCard: async (docId: string): Promise<DocCard> => {
        const res = await fetch(`${API_BASE_URL}/api/docs/${docId}`, {
            headers: getHeaders()
        });
        if (!res.ok) throw new Error("Fetch Doc Card failed");
        return await res.json();
    }
};
