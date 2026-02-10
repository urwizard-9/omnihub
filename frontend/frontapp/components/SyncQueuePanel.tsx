import React from 'react';
import { Loader2, CheckCircle2, XCircle, Trash2, FolderSync, FileText, ChevronDown, ChevronUp } from 'lucide-react';
import { useOmniHub } from '../context/OmniHubContext';

interface SyncQueuePanelProps {
    statusData?: any; // kept for legacy compat if needed, but we rely on context queue now
}

const SyncQueuePanel: React.FC<SyncQueuePanelProps> = () => {
    const { uploadQueue, removeUpload, lastProcessedFile } = useOmniHub();
    const [isCollapsed, setIsCollapsed] = React.useState(false);

    if (!uploadQueue || uploadQueue.length === 0) return null;

    return (
        <div className="mt-4 mx-4 bg-white/5 border border-white/5 rounded-xl shadow-lg overflow-hidden transition-all duration-300">
            {/* Header */}
            <div
                className="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-white/5 transition-colors"
                onClick={() => setIsCollapsed(!isCollapsed)}
            >
                <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Upload Queue</span>
                    <span className="bg-white/10 px-1.5 py-0.5 rounded text-[10px] text-slate-300">{uploadQueue.length}</span>
                </div>
                <button className="text-slate-500 hover:text-white transition-colors">
                    {isCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                </button>
            </div>

            {/* Body */}
            {!isCollapsed && (
                <div className="p-4 pt-0 space-y-4 animate-in slide-in-from-top-2">

                    <div className="space-y-3 max-h-[300px] overflow-y-auto scrollbar-thin scrollbar-thumb-white/10 pr-1">
                        {uploadQueue.map((item) => (
                            <div key={item.id} className="group relative bg-[#13141F] border border-white/5 rounded-lg p-3 hover:border-white/10 transition-all">

                                {/* Status Icon */}
                                <div className="absolute top-3 right-3 flex items-center gap-2">
                                    <span className="text-[10px] text-slate-500">{item.progress}%</span>
                                    <button
                                        onClick={() => removeUpload(item.id, item.status !== 'completed')}
                                        className={`p-1.5 rounded-full transition-colors ${item.status === 'completed'
                                            ? 'text-slate-500 hover:text-white hover:bg-white/10'
                                            : 'text-red-400 hover:text-red-200 hover:bg-red-500/10'
                                            }`}
                                        title={item.status === 'completed' ? "Clear from list" : "Cancel / Discard"}
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>

                                <div className="flex items-start gap-3">
                                    <div className="mt-0.5">
                                        {item.status === 'processing' ? (
                                            <Loader2 size={16} className="text-indigo-500 animate-spin" />
                                        ) : item.status === 'completed' ? (
                                            <CheckCircle2 size={16} className="text-emerald-500" />
                                        ) : item.status === 'cancelled' ? (
                                            <XCircle size={16} className="text-slate-500" />
                                        ) : (
                                            <XCircle size={16} className="text-red-500" />
                                        )}
                                    </div>

                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 mb-1">
                                            {item.type === 'folder' ? <FolderSync size={12} className="text-blue-400" /> : <FileText size={12} className="text-slate-400" />}
                                            <h4 className="text-sm font-medium text-slate-200 truncate pr-6" title={item.name}>
                                                {item.name}
                                            </h4>
                                        </div>

                                        <div className="flex justify-between items-center text-[10px] text-slate-500 mb-1.5">
                                            <span className="capitalize">{item.status}</span>
                                            {item.status === 'processing' && (
                                                <span className="font-mono text-indigo-400">{item.progress}%</span>
                                            )}
                                        </div>

                                        {item.status === 'processing' && (
                                            <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                                                <div
                                                    className="h-full bg-indigo-500 transition-all duration-300"
                                                    style={{ width: `${item.progress}%` }}
                                                />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default SyncQueuePanel;
