import React, { useEffect, useState } from 'react';
import { Folder, FileText, Trash2, RefreshCw, AlertCircle, ExternalLink, Clock } from 'lucide-react';
import { BackendAPI } from '../services/dataService';
import { useOmniHub } from '../context/OmniHubContext';

// Using simple string parsing to avoid dep.

interface MonitoredItem {
    id: string;
    name: string;
    link?: string;
    status: 'active' | 'trashed' | 'error' | 'pending';
    type?: 'folder' | 'file';
    error?: string;
    last_synced?: string;
}

interface MonitoredFolderListProps {
    refreshTrigger?: number;
    embedded?: boolean;
    onLoadingChange?: (loading: boolean) => void;
}

const MonitoredFolderList: React.FC<MonitoredFolderListProps> = ({ refreshTrigger = 0, embedded = false, onLoadingChange }) => {
    const { token, userProfile, removeUpload } = useOmniHub();
    const [items, setItems] = useState<MonitoredItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [removingId, setRemovingId] = useState<string | null>(null);

    const fetchItems = async () => {
        if (!token) return;
        setLoading(true);
        if (onLoadingChange) onLoadingChange(true);
        try {
            const list = await BackendAPI.getMonitoredFolders(token);
            setItems(list);
        } catch (e) {
            console.error("Failed to load monitored items", e);
        } finally {
            setLoading(false);
            if (onLoadingChange) onLoadingChange(false);
        }
    };

    useEffect(() => {
        fetchItems();
    }, [token, userProfile?.monitored_folder_ids, refreshTrigger]);

    const handleUnsync = async (item: MonitoredItem) => {
        if (!token) return;
        const msg = item.type === 'file'
            ? `Stop monitoring file "${item.name}"?\n\nUpdates will no longer be tracked.`
            : `Stop syncing folder "${item.name}"?\n\nExisting files will remain, but new changes won't be synced.`;

        if (!confirm(msg)) return;

        setRemovingId(item.id);
        try {
            await BackendAPI.unsyncFolder(item.id, token, true);
            removeUpload(item.id, true);
            await fetchItems();
        } catch (e: any) {
            alert(`Failed to unsync: ${e.message}`);
        } finally {
            setRemovingId(null);
        }
    };

    const formatTime = (isoString?: string) => {
        if (!isoString) return 'Never';
        try {
            const date = new Date(isoString);
            return date.toLocaleString(); // Simple local time
        } catch {
            return isoString;
        }
    };

    if (!token) return null;

    if (embedded) {
        return (
            <div className="h-full overflow-y-auto p-2 space-y-2 scrollbar-thin">
                {items.length === 0 && !loading && (
                    <div className="text-center py-4 text-slate-500 text-xs">
                        No monitored items.
                    </div>
                )}

                {items.map(item => (
                    <div key={item.id} className="group bg-black/20 border border-white/5 p-3 rounded-lg hover:bg-white/5 transition-all">
                        <div className="flex justify-between items-start gap-3">
                            <div className="overflow-hidden flex-1">
                                <div className="flex items-center gap-2 mb-1">
                                    {item.type === 'file' ? (
                                        <FileText size={14} className="text-blue-400 shrink-0" />
                                    ) : (
                                        <Folder size={14} className="text-yellow-400 shrink-0" />
                                    )}
                                    <span className={`text-sm font-medium truncate ${item.status === 'error' ? 'text-red-400' : 'text-slate-200'}`}>
                                        {item.name}
                                    </span>
                                    {item.link && (
                                        <a href={item.link} target="_blank" rel="noreferrer" className="text-slate-600 hover:text-indigo-400">
                                            <ExternalLink size={10} />
                                        </a>
                                    )}
                                </div>
                                <div className="flex items-center gap-2 text-[10px] text-slate-500">
                                    <span className="font-mono truncate max-w-[80px]">{item.id}</span>
                                    {item.last_synced && (
                                        <span className="flex items-center gap-1 text-slate-400" title="Last Synced">
                                            <Clock size={8} />
                                            {formatTime(item.last_synced).split(',')[1] || 'Just now'}
                                        </span>
                                    )}
                                </div>

                                {item.status === 'trashed' && (
                                    <span className="inline-block mt-1 text-[10px] bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded">Trash on Drive</span>
                                )}
                                {item.error && (
                                    <div className="flex items-center gap-1 mt-1 text-[10px] text-red-400">
                                        <AlertCircle size={10} />
                                        <span className="truncate">{item.error}</span>
                                    </div>
                                )}
                            </div>

                            <button
                                onClick={() => handleUnsync(item)}
                                disabled={removingId === item.id}
                                className="p-2 bg-red-500/10 text-red-400 rounded-lg hover:bg-red-500 hover:text-white transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                                title="Stop Syncing / Unlink"
                            >
                                {removingId === item.id ? (
                                    <RefreshCw size={14} className="animate-spin" />
                                ) : (
                                    <Trash2 size={14} />
                                )}
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full bg-[#1E1F2E] border border-white/5 rounded-2xl shadow-xl overflow-hidden">
            <div className="p-4 border-b border-white/5 flex items-center justify-between bg-black/20">
                <div className="flex items-center gap-2">
                    <RefreshCw size={16} className="text-indigo-400" />
                    <h3 className="font-bold text-slate-200 text-sm">Active Syncs</h3>
                </div>
                <button
                    onClick={fetchItems}
                    disabled={loading}
                    className="p-1 hover:bg-white/5 rounded text-slate-500 hover:text-white transition-colors"
                >
                    <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
                </button>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-2 scrollbar-thin">
                {items.length === 0 && !loading && (
                    <div className="text-center py-8 text-slate-500 text-xs">
                        No monitored items.
                    </div>
                )}

                {items.map(item => (
                    <div key={item.id} className="group bg-black/20 border border-white/5 p-3 rounded-lg hover:bg-white/5 transition-all">
                        <div className="flex justify-between items-start gap-3">
                            <div className="overflow-hidden flex-1">
                                <div className="flex items-center gap-2 mb-1">
                                    {item.type === 'file' ? (
                                        <FileText size={14} className="text-blue-400 shrink-0" />
                                    ) : (
                                        <Folder size={14} className="text-yellow-400 shrink-0" />
                                    )}
                                    <span className={`text-sm font-medium truncate ${item.status === 'error' ? 'text-red-400' : 'text-slate-200'}`}>
                                        {item.name}
                                    </span>
                                    {item.link && (
                                        <a href={item.link} target="_blank" rel="noreferrer" className="text-slate-600 hover:text-indigo-400">
                                            <ExternalLink size={10} />
                                        </a>
                                    )}
                                </div>
                                <div className="flex items-center gap-2 text-[10px] text-slate-500">
                                    <span className="font-mono truncate max-w-[80px]">{item.id}</span>
                                    {item.last_synced && (
                                        <span className="flex items-center gap-1 text-slate-400" title="Last Synced">
                                            <Clock size={8} />
                                            {formatTime(item.last_synced).split(',')[1] || 'Just now'}
                                        </span>
                                    )}
                                </div>

                                {item.status === 'trashed' && (
                                    <span className="inline-block mt-1 text-[10px] bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded">Trash on Drive</span>
                                )}
                                {item.error && (
                                    <div className="flex items-center gap-1 mt-1 text-[10px] text-red-400">
                                        <AlertCircle size={10} />
                                        <span className="truncate">{item.error}</span>
                                    </div>
                                )}
                            </div>

                            <button
                                onClick={() => handleUnsync(item)}
                                disabled={removingId === item.id}
                                className="p-2 bg-red-500/10 text-red-400 rounded-lg hover:bg-red-500 hover:text-white transition-colors opacity-0 group-hover:opacity-100 focus:opacity-100"
                                title="Stop Syncing / Unlink"
                            >
                                {removingId === item.id ? (
                                    <RefreshCw size={14} className="animate-spin" />
                                ) : (
                                    <Trash2 size={14} />
                                )}
                            </button>
                        </div>
                    </div>
                ))}
            </div>

            <div className="p-2 border-t border-white/5 bg-black/20 text-[10px] text-slate-500 text-center">
                {items.length} monitored items
            </div>
        </div>
    );
};

export default MonitoredFolderList;
