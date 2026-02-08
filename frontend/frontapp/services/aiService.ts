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
    getGraphInit: async (params: { mode?: string, max_concepts?: number, max_edges?: number, include_docs?: boolean } = {}): Promise<GraphData> => {
        const query = new URLSearchParams({
            mode: params.mode || 'overview',
            max_concepts: (params.max_concepts || 50).toString(),
            max_edges: (params.max_edges || 160).toString(),
            include_docs: (params.include_docs || false).toString()
        }).toString();

        const res = await fetch(`${API_BASE_URL}/api/graph/init?${query}`, {
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

    getGraphSubgraph: async (params: {
        center_concept_id: string,
        mode?: string,
        doc_limit?: number,
        concepts_per_doc?: number,
        docs_per_concept?: number,
        max_total_nodes?: number,
        max_total_edges?: number
    }): Promise<GraphData> => {
        const query = new URLSearchParams({
            center_concept_id: params.center_concept_id,
            mode: params.mode || 'cascade',
            doc_limit: (params.doc_limit || 20).toString(),
            concepts_per_doc: (params.concepts_per_doc || 6).toString(),
            docs_per_concept: (params.docs_per_concept || 5).toString(),
            max_total_nodes: (params.max_total_nodes || 600).toString(),
            max_total_edges: (params.max_total_edges || 1200).toString()
        }).toString();

        const res = await fetch(`${API_BASE_URL}/api/graph/subgraph?${query}`, {
            headers: getHeaders()
        });
        if (!res.ok) throw new Error("Graph Subgraph failed");
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
