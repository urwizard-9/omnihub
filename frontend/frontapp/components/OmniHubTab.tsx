import React, { useState } from 'react';
import { useOmniHub } from '../context/OmniHubContext'; // Keep for Upload/Global status
import { MessageSquare, FolderTree, Loader2 } from 'lucide-react';

// New AI Components
import RAGSearchPanel from './AI/RAGSearchPanel';
import DocTreeBrowser from './AI/DocTreeBrowser';
import KnowledgeGraph from './AI/KnowledgeGraph';
import DocDetailDrawer from './AI/DocDetailDrawer';
import SyncQueuePanel from './SyncQueuePanel';

type LeftTab = 'chat' | 'explorer';

const OmniHubTab: React.FC = () => {
    const [leftTab, setLeftTab] = useState<LeftTab>('chat');
    const { aiStatus, syncStatusData, isSyncLocked } = useOmniHub();
    const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

    return (
        <div className="flex flex-1 overflow-hidden relative">
            {/* Left Panel */}
            <div className="w-[360px] shrink-0 bg-[#13141F] border-r border-white/5 flex flex-col z-10 shadow-2xl relative">

                {/* Tab Navigation */}
                <div className="px-4 pt-4 pb-2 bg-[#13141F]">
                    <div className="flex bg-white/5 p-1 rounded-xl border border-white/5">
                        <button
                            onClick={() => setLeftTab('chat')}
                            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold transition-all ${leftTab === 'chat'
                                ? 'bg-[#1E1F2E] text-white shadow-lg border border-white/5'
                                : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                                }`}
                        >
                            <MessageSquare size={14} /> AI Chat
                        </button>
                        <button
                            onClick={() => setLeftTab('explorer')}
                            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold transition-all ${leftTab === 'explorer'
                                ? 'bg-[#1E1F2E] text-white shadow-lg border border-white/5'
                                : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                                }`}
                        >
                            <FolderTree size={14} /> Docs Tree
                        </button>
                    </div>
                </div>

                {/* Left Content */}
                <div className="flex-1 overflow-hidden relative">
                    {leftTab === 'chat' ? (
                        <>
                            <RAGSearchPanel onCitationClick={(id) => setSelectedDocId(id)} />

                            {/* Sync Active Queue */}
                            <SyncQueuePanel statusData={syncStatusData} />

                            {/* Status Legend */}
                            {(aiStatus === 'completed' || aiStatus === 'idle') && (
                                <div className="mx-6 mt-4 p-4 bg-white/5 rounded-xl border border-white/5 space-y-2">
                                    <h4 className="text-[10px] uppercase font-bold text-slate-400 tracking-wider mb-2">Sync Status Guide</h4>
                                    <div className="flex items-center gap-2 text-[10px] text-slate-300">
                                        <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
                                        <span>Success: Processed & Analyzed</span>
                                    </div>
                                    <div className="flex items-center gap-2 text-[10px] text-slate-300">
                                        <div className="w-2 h-2 rounded-full bg-slate-500"></div>
                                        <span>Skipped: Unchanged (Optimization)</span>
                                    </div>
                                    <div className="flex items-center gap-2 text-[10px] text-slate-300">
                                        <div className="w-2 h-2 rounded-full bg-red-500"></div>
                                        <span>Failed: Unsupported Format (e.g. Sheet)</span>
                                    </div>
                                </div>
                            )}
                        </>
                    ) : (
                        <DocTreeBrowser onFileClick={(id) => setSelectedDocId(id)} />
                    )}
                </div>
            </div>

            {/* Main Content Area */}
            <div className="flex-1 bg-[#09090b] relative overflow-hidden flex flex-col">

                {/* Loading State: Syncing (Removed Blocking Overlay) */}
                {/* Progress is now shown in SyncQueuePanel in the Sidebar */}

                {/* Loading State: Analyzing */}
                {/* Header Badge: Analyzing (Phase B - Unlocked) */}
                {aiStatus === 'analyzing' && (
                    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-40 bg-indigo-500/10 border border-indigo-500/20 backdrop-blur-md px-4 py-1.5 rounded-full flex items-center gap-2 shadow-lg animate-in fade-in slide-in-from-top-4">
                        <div className="flex items-center gap-1">
                            <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse"></div>
                            <div className="w-1.5 h-1.5 bg-purple-500 rounded-full animate-pulse delay-75"></div>
                        </div>
                        <span className="text-[10px] font-bold text-indigo-200 tracking-wider uppercase">AI Knowledge Generation Active</span>
                    </div>
                )}

                {/* Header Badge: File Ingestion (Phase A - Unlocked) */}
                {isSyncLocked && aiStatus !== 'analyzing' && (
                    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-40 bg-amber-500/10 border border-amber-500/20 backdrop-blur-md px-4 py-1.5 rounded-full flex items-center gap-2 shadow-lg animate-in fade-in slide-in-from-top-4">
                        <Loader2 size={12} className="text-amber-500 animate-spin" />
                        <span className="text-[10px] font-bold text-amber-200 tracking-wider uppercase">Receiving Files...</span>
                    </div>
                )}

                {/* Default State: Show Graph Only when Ready or Mocked */}
                {(aiStatus === 'completed' || aiStatus === 'idle') && (
                    <>
                        <KnowledgeGraph onDocClick={(id) => setSelectedDocId(id)} />
                    </>
                )}

                {/* Doc Detail Overlay */}
                {selectedDocId && (
                    <div className="absolute top-0 right-0 w-[450px] h-full shadow-2xl z-20 border-l border-white/10 pointer-events-none">
                        {/* pointer-events-none wrapper to let clicks pass through if needed, but Drawer has pointer-events-auto */}
                        <div className="pointer-events-auto h-full">
                            <DocDetailDrawer docId={selectedDocId} onClose={() => setSelectedDocId(null)} />
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default OmniHubTab;