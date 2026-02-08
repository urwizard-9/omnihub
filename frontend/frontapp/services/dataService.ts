
import { ConceptNode, DocRecord, Role, SecurityLevel, DriveFile } from '../types';

// --- Constants (Fakes removed) ---


// --- Version Regex & Logic ---
const REGEX_VER_NUM = /\b(v|ver|version|rev|re|r)[\s._-]*(\d{1,3})\b/gi;
const REGEX_STATUS_FINAL = /(final|finalized|definitive|최종(본|안)?|확정(본|안)?|완료본|제출본)/gi;
const REGEX_STATUS_APPROVED = /(approved|signed|executed|승인(본)?|서명(본)?|날인(본)?|결재(완료)?)/gi;
const REGEX_STATUS_REVISED = /(update(d)?|revis(ed|ion)?|수정(본|안)?|재수정(본)?|변경(본)?|개정(본)?)/gi;
const REGEX_STATUS_DRAFT = /(draft|tmp|temp|초안|초본|임시(본)?|작업본|검토본|내부용)/gi;
const REGEX_DATE_PREFIX = /^\d{4}([._-]?\d{2}){0,2}[._-]?/;
const REGEX_BRACKET_PREFIX = /^\s*[\[\(].*?[\]\)]\s*/;

export interface VersionMeta {
    versionNumber?: number;
    versionStatus?: 'final' | 'approved' | 'revised' | 'draft' | null;
    rawTokens: string[];
}

export const extractVersionMeta = (fileName: string): VersionMeta => {
    const rawTokens: string[] = [];
    let versionNumber: number | undefined;
    let versionStatus: VersionMeta['versionStatus'] = null;

    const verMatch = Array.from(fileName.matchAll(REGEX_VER_NUM));
    if (verMatch.length > 0) {
        const lastMatch = verMatch[verMatch.length - 1];
        versionNumber = parseInt(lastMatch[2], 10);
        rawTokens.push(lastMatch[0]);
    }

    if (fileName.match(REGEX_STATUS_FINAL)) versionStatus = 'final';
    else if (fileName.match(REGEX_STATUS_APPROVED)) versionStatus = 'approved';
    else if (fileName.match(REGEX_STATUS_REVISED)) versionStatus = 'revised';
    else if (fileName.match(REGEX_STATUS_DRAFT)) versionStatus = 'draft';

    return { versionNumber, versionStatus, rawTokens };
};

export const computeGroupKey = (fileName: string): string => {
    if (!fileName) return "untitled";
    let base = fileName.replace(/\.[^/.]+$/, "");
    base = base.replace(REGEX_BRACKET_PREFIX, "");
    base = base.replace(REGEX_DATE_PREFIX, "");
    base = base.replace(REGEX_VER_NUM, "");
    base = base.replace(REGEX_STATUS_FINAL, "");
    base = base.replace(REGEX_STATUS_APPROVED, "");
    base = base.replace(REGEX_STATUS_REVISED, "");
    base = base.replace(REGEX_STATUS_DRAFT, "");
    base = base.replace(/[._\-]+/g, " ");
    return base.trim().toLowerCase();
};

const versionSort = (a: DocRecord, b: DocRecord) => {
    const metaA = extractVersionMeta(a.name);
    const metaB = extractVersionMeta(b.name);
    const statusScore = (s: string | null | undefined) => {
        if (s === 'final') return 4;
        if (s === 'approved') return 3;
        if (s === 'revised') return 2;
        if (s === 'draft') return 1;
        return 0;
    };
    const sA = statusScore(metaA.versionStatus);
    const sB = statusScore(metaB.versionStatus);
    if (sA !== sB) return sB - sA;
    const vA = metaA.versionNumber || 0;
    const vB = metaB.versionNumber || 0;
    if (vA !== vB) return vB - vA;
    return b.updatedAt - a.updatedAt;
};

export const getVersionRangeText = (docs: DocRecord[]): string => {
    if (docs.length === 0) return '';
    const sorted = [...docs].sort(versionSort);
    const representative = sorted[0];
    const repMeta = extractVersionMeta(representative.name);
    const repText = repMeta.versionStatus ? repMeta.versionStatus.toUpperCase() : (repMeta.versionNumber ? `v${repMeta.versionNumber}` : 'Latest');
    const others = sorted.slice(1);
    const oldest = others[others.length - 1];
    if (!oldest) return repText;
    const oldMeta = extractVersionMeta(oldest.name);
    const oldText = oldMeta.versionNumber ? `v${oldMeta.versionNumber}` : (oldMeta.versionStatus || 'v1');
    return `${oldText} ~ ${repText}`;
};

export interface GroupedDocs {
    groups: Record<string, DocRecord[]>;
    singles: DocRecord[];
}

export const groupDocsByVersion = (docs: DocRecord[]): GroupedDocs => {
    const groups: Record<string, DocRecord[]> = {};
    const singles: DocRecord[] = [];
    const tempMap: Record<string, DocRecord[]> = {};
    docs.forEach(doc => {
        const base = computeGroupKey(doc.name);
        if (base.length < 2) {
            singles.push(doc);
            return;
        }
        if (!tempMap[base]) tempMap[base] = [];
        tempMap[base].push(doc);
    });
    Object.entries(tempMap).forEach(([key, list]) => {
        if (list.length >= 2) {
            groups[key] = list.sort(versionSort);
        } else {
            singles.push(...list);
        }
    });
    return { groups, singles };
};

// --- Helpers (Random generators removed) ---




// --- Actual Tree Helpers ---
export interface ActualFolderNode {
    folderName: string;
    totalDocs: number;
    docs: DocRecord[];
}

export const getActualTreeStructure = (docs: DocRecord[], filterText: string = ''): ActualFolderNode[] => {
    const map: Record<string, DocRecord[]> = {};

    docs.forEach(doc => {
        const folder = doc.actualPath || "Uncategorized";
        if (!map[folder]) map[folder] = [];
        map[folder].push(doc);
    });

    const result = Object.entries(map).map(([folderName, folderDocs]) => {
        folderDocs.sort((a, b) => b.updatedAt - a.updatedAt);
        return {
            folderName,
            totalDocs: folderDocs.length,
            docs: folderDocs
        };
    });

    result.sort((a, b) => a.folderName.localeCompare(b.folderName));

    if (filterText) {
        const lowerFilter = filterText.toLowerCase();
        return result.map(node => ({
            ...node,
            docs: node.docs.filter(d =>
                d.name.toLowerCase().includes(lowerFilter) ||
                node.folderName.toLowerCase().includes(lowerFilter)
            )
        })).filter(node => node.docs.length > 0 || node.folderName.toLowerCase().includes(lowerFilter));
    }

    return result;
};

export const getTopTags = (docs: DocRecord[]): string[] => {
    const counts: Record<string, number> = {};
    docs.forEach(d => d.tags.forEach(t => counts[t] = (counts[t] || 0) + 1));
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 10).map(e => e[0]);
};

// --- REAL BACKEND API INTEGRATION ---

// DriveFile is imported from ../types

// [CONFIG] API Base URL
// Local Development: 'http://localhost:8000' or dynamic for network sharing
// Production (Cloud Run): 'https://omnihub-backend-707724932002.asia-northeast3.run.app'
// If accessing via 172.24..., we must call backend at 172.24... too to avoid CORS/Mixed issues sometimes.
const getBaseUrl = () => {
    // 1. Local Development (runs against local backend)
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        // Use local backend for development
        return 'http://localhost:8000';
        // If you want to test against Cloud Run from localhost, use:
        // return 'https://omnihub-backend-707724932002.asia-northeast3.run.app';
    }

    // 2. Production / Deployed (Must point to Cloud Run)
    return 'https://omnihub-backend-707724932002.asia-northeast3.run.app';
};
export const API_BASE_URL = getBaseUrl();
// const API_BASE_URL = 'https://omnihub-backend-707724932002.asia-northeast3.run.app';

// --- Helper: Interceptor Fetch ---
const apiFetch = async (url: string, options: RequestInit = {}) => {
    try {
        const res = await fetch(url, options);

        if (!res.ok) {
            let errorData: any = {};
            try {
                errorData = await res.json();
            } catch (e) {
                errorData = { message: res.statusText };
            }

            // [Auto-Toast Logic]
            if (errorData.action === 'contact_admin') {
                window.dispatchEvent(new CustomEvent('omnihub-toast', {
                    detail: {
                        type: 'error',
                        title: 'Server Configuration Error',
                        message: errorData.message || "Critical system error occurred.",
                        action: 'contact_admin'
                    }
                }));
            } else if (errorData.action === 'retry') {
                window.dispatchEvent(new CustomEvent('omnihub-toast', {
                    detail: {
                        type: 'warning',
                        title: 'Service Busy',
                        message: errorData.message || "Service is temporarily unavailable.",
                        action: 'retry'
                    }
                }));
            }

            // Re-throw for local handling if needed
            throw new Error(errorData.detail?.message || errorData.detail || "API Error");
        }
        return await res.json();
    } catch (e: any) {
        // Network errors (fetch failed entirely)
        if (e.message === "Failed to fetch") {
            window.dispatchEvent(new CustomEvent('omnihub-toast', {
                detail: {
                    type: 'error',
                    title: 'Network Error',
                    message: "Cannot connect to server. Check your internet connection.",
                }
            }));
        }
        throw e;
    }
};

// Helper: Flatten Tree to DocRecord[]
const flattenTreeToDocs = (node: any, docs: DocRecord[] = []) => {
    if (node.files) {
        node.files.forEach((f: any) => {
            docs.push({
                id: f.doc_id || f.id || crypto.randomUUID(),
                name: f.name,
                folderPath: node.current_path || "/", // Approx
                actualPath: "Unknown",
                driveUrl: f.webViewLink || "",
                tags: [],
                period: "2024-H1", // Default
                owner: "Unknown",
                updatedAt: Date.now(),
                sizeKB: 0,
                ext: f.mime_type || 'unknown',
                security: 'medium',
                aiSummary3: [],
                conceptIds: [],
                status: 'idle',
                relatedFolderPaths: [],
                textExcerpt: ''
            });
        });
    }
    if (node.folders) {
        node.folders.forEach((child: any) => flattenTreeToDocs(child, docs));
    }
    if (node.children) { // specific to virtual-tree response structure
        node.children.forEach((child: any) => {
            if (!child.is_folder && child.id) {
                // It's a file
                docs.push({
                    id: child.id,
                    name: child.name,
                    folderPath: node.name === 'Root' ? '/' : `/${node.name}`,
                    actualPath: "Unknown",
                    driveUrl: "",
                    tags: [], // Metadata missing in simple tree
                    period: "2024-H1",
                    owner: "Unknown",
                    updatedAt: Date.now(),
                    sizeKB: 0, // Missing
                    ext: child.mime_type || 'unknown',
                    security: 'medium',
                    aiSummary3: [],
                    conceptIds: [],
                    status: 'idle',
                    relatedFolderPaths: [],
                    textExcerpt: ''
                });
            } else {
                flattenTreeToDocs(child, docs);
            }
        });
    }
    return docs;
};

export const BackendAPI = {
    // 1. Google Login (Exchange Code for Tokens)
    exchangeToken: async (googleCode: string): Promise<{ access_token: string }> => {
        return apiFetch(`${API_BASE_URL}/auth/google`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: googleCode })
        });
    },

    // 2. Drive Proxy (List Files or Search)
    getDriveProxy: async (folderId: string = "root", token: string | null, query?: string): Promise<DriveFile[]> => {
        if (!token) return [];
        let url = `${API_BASE_URL}/files/drive/proxy?folder_id=${folderId}`;
        if (query) {
            url += `&q=${encodeURIComponent(query)}`;
        }

        const data = await apiFetch(url, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        return data.files || [];
    },

    // 3. Sync Folder Action
    syncFolder: async (folderId: string, token: string | null) => {
        if (!token) throw new Error("No Token");
        await apiFetch(`${API_BASE_URL}/drive/sync-folder`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ folder_id: folderId })
        });
    },

    // 3.1 Ingest Single File
    ingestFile: async (fileId: string, token: string | null) => {
        if (!token) throw new Error("No Token");
        return apiFetch(`${API_BASE_URL}/drive/ingest`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ file_id: fileId })
        });
    },

    // 3.2 Auto-Register Webhook (Self)
    registerWatch: async (token: string | null) => {
        if (!token) throw new Error("No Token");
        return apiFetch(`${API_BASE_URL}/drive/watch/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({})
        });
    },

    // 3.5 Unsync Folder (Stop Sync)
    unsyncFolder: async (folderId: string, token: string | null, abort: boolean = false) => {
        if (!token) throw new Error("No Token");
        await apiFetch(`${API_BASE_URL}/drive/sync-folder?folder_id=${folderId}&abort=${abort}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            // Body is optional for DELETE but some proxies strip it. 
            // We moved folder_id to query param for safety, but keeping body for backward compatibility if needed.
            body: JSON.stringify({ folder_id: folderId })
        });
    },

    getMonitoredFolders: async (token: string | null) => {
        if (!token) return [];
        return apiFetch(`${API_BASE_URL}/files/drive/monitored-folders?_t=${Date.now()}`, { // Anti-cache
            headers: {
                'Authorization': `Bearer ${token}`,
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache'
            }
        });
    },

    // 4. Check Sync Status (Polling)
    getSyncStatus: async (folderId: string, token: string | null) => {
        if (!token) return { status: 'idle' };
        try {
            return await apiFetch(`${API_BASE_URL}/drive/status/${folderId}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
        } catch {
            return { status: 'error' };
        }
    },

    // 4.1 Check Item Status (File/Folder) - Single check
    checkItemSyncStatus: async (id: string, token: string | null) => {
        if (!token) return { exists: false, status: 'unknown' };
        try {
            return await apiFetch(`${API_BASE_URL}/files/${id}/sync-status`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
        } catch {
            return { exists: false, status: 'error' };
        }
    },

    // 5. User Management (Profile & Admin)
    fetchCurrentUser: async (token: string | null) => {
        if (!token) throw new Error("No Token");
        return apiFetch(`${API_BASE_URL}/users/me`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    },

    getUsers: async (token: string | null) => {
        if (!token) throw new Error("No Token");
        return apiFetch(`${API_BASE_URL}/admin/users?limit=100`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    },

    updateUser: async (email: string, updates: any, token: string | null) => {
        if (!token) throw new Error("No Token");
        return apiFetch(`${API_BASE_URL}/admin/users/${email}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(updates)
        });
    },

    // 6. System Health & Logs
    getSystemHealth: async (token: string | null) => {
        if (!token) throw new Error("No Token");
        return apiFetch(`${API_BASE_URL}/admin/system-health`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    },

    getSystemErrors: async (token: string | null, limit: number = 50) => {
        if (!token) return [];
        return apiFetch(`${API_BASE_URL}/admin/system-errors?limit=${limit}`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
    },

    // 8. Document Status Update
    updateDocumentStatus: async (docId: string, status: string, token: string | null) => {
        if (!token) throw new Error("No Token");
        return apiFetch(`${API_BASE_URL}/api/docs/${docId}/status`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ status, reason: "Updated via UI" })
        });
    },

    // 7. Initial Data hydration (Global)
    fetchGlobalInitialData: async (token: string | null) => {
        if (!token) throw new Error("No Token");

        // Parallel Fetch: Graph Init (for concepts), Virtual Tree (for docs)
        // Note: Profile is fetched separately in Context
        const [graphData, treeData] = await Promise.all([
            apiFetch(`${API_BASE_URL}/api/graph/init?limit=50`, { headers: { 'Authorization': `Bearer ${token}` } }),
            apiFetch(`${API_BASE_URL}/files/virtual-tree`, { headers: { 'Authorization': `Bearer ${token}` } })
        ]);

        // Transform Graph Nodes to Concepts
        const concepts = (graphData?.nodes || []).map((n: any) => ({
            id: n.id,
            label: n.label || n.id,
            createdAt: Date.now()
        }));

        // Transform Virtual Tree to DocRecord List
        const docs: DocRecord[] = [];
        if (treeData) {
            flattenTreeToDocs(treeData, docs);
        }

        return {
            concepts,
            docs,
            logMsg: `Global Data Loaded: ${concepts.length} concepts, ${docs.length} docs found.`
        };
    }
};
