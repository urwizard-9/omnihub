import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ConceptNode, DocRecord } from '../types';
import { ActualFolderNode } from '../services/dataService';
import GraphVisualizer from './GraphVisualizer';
import DocDetailDrawer from './DocDetailDrawer';
import { useOmniHub } from '../context/OmniHubContext';
import { Search, Sparkles, ArrowRight, History, CloudUpload, FileSearch, Bot, Loader2, MessageSquare, FolderTree, ChevronRight, ChevronDown, Filter, Database, FileText, Star, Cpu, Terminal, Command, Hash, CheckCircle2 } from 'lucide-react';

interface RagResponse {
  query: string; // Track the query that generated this response
  conclusion: string;
  evidenceSummary: string;
  action: string;
}

export interface VirtualFilterState {
    security: string[];
    status: string[];
    years: string[];
    tags: string[];
}

type LeftTab = 'chat' | 'explorer';

const INITIAL_FOLDER_LIMIT = 8;
const LOAD_MORE_STEP = 20;

// --- TREE COMPONENTS (Memoization removed for reliability) ---

interface TreeDocItemProps { 
    doc: DocRecord; 
    isSelected: boolean; 
    onClick: (doc: DocRecord) => void;
}

const TreeDocItem: React.FC<TreeDocItemProps> = ({ 
    doc, 
    isSelected, 
    onClick 
}) => (
    <div 
        id={`tree-doc-${doc.id}`}
        onClick={(e) => { e.stopPropagation(); onClick(doc); }}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-md cursor-pointer text-xs transition-all group/doc border border-transparent ${
            isSelected
            ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30 shadow-[0_0_10px_rgba(99,102,241,0.2)] font-bold translate-x-1' 
            : 'text-slate-400 hover:text-indigo-200 hover:bg-white/5'
        }`}
    >
        <FileText size={12} className={`shrink-0 ${isSelected ? 'text-indigo-400' : 'opacity-40 group-hover/doc:opacity-100'}`} />
        <span className="truncate tracking-tight">{doc.name}</span>
    </div>
);

interface TreeFolderItemProps { 
    node: ActualFolderNode; 
    isExpanded: boolean; 
    limit: number; 
    selectedDocId: string | undefined; 
    onToggle: (name: string, e: React.MouseEvent) => void;
    onLoadMore: (name: string, e: React.MouseEvent) => void;
    onDocClick: (doc: DocRecord) => void;
}

const TreeFolderItem: React.FC<TreeFolderItemProps> = ({ 
    node, 
    isExpanded, 
    limit, 
    selectedDocId, 
    onToggle, 
    onLoadMore, 
    onDocClick 
}) => {
    const visibleDocs = node.docs.slice(0, limit);
    const hasMore = node.docs.length > limit;
    const remaining = node.docs.length - limit;

    return (
        <div className="animate-in fade-in slide-in-from-left-2 duration-200">
            <div 
                onClick={(e) => onToggle(node.folderName, e)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all border border-transparent group ${
                    isExpanded 
                    ? 'bg-amber-500/10 border-amber-500/20 text-amber-200' 
                    : 'hover:bg-white/5 text-slate-400'
                }`}
            >
                <div className="p-0.5 text-slate-500 hover:text-white transition-colors">
                    {isExpanded ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}
                </div>
                
                <Database size={14} className={isExpanded ? "text-amber-400 drop-shadow-[0_0_5px_rgba(251,191,36,0.5)]" : "text-slate-600 group-hover:text-amber-500/50"} />
                
                <span className="text-xs font-bold truncate flex-1 tracking-tight">{node.folderName}</span>
                <span className="text-[9px] bg-white/5 px-1.5 py-0.5 rounded border border-white/5 text-slate-500 font-mono">{node.totalDocs}</span>
            </div>

            {isExpanded && (
                <div className="ml-4 pl-3 border-l border-white/10 mt-1 mb-2 space-y-0.5">
                    {visibleDocs.map(doc => (
                        <TreeDocItem 
                            key={doc.id} 
                            doc={doc} 
                            isSelected={selectedDocId === doc.id} 
                            onClick={onDocClick} 
                        />
                    ))}
                    
                    {hasMore && (
                        <button 
                            onClick={(e) => onLoadMore(node.folderName, e)}
                            className="w-full text-left px-3 py-1.5 text-[10px] text-amber-500/70 hover:text-amber-400 hover:bg-white/5 rounded transition-colors italic font-medium"
                        >
                            + {remaining} more files...
                        </button>
                    )}
                    
                    {node.docs.length === 0 && (
                        <div className="px-3 py-1.5 text-[10px] text-slate-600 italic">Empty folder</div>
                    )}
                </div>
            )}
        </div>
    );
};

// --- ActualTree Component ---

interface ActualTreeProps {
    treeData: ActualFolderNode[];
    expandedFolders: Set<string>;
    folderLimits: Record<string, number>;
    selectedDocId: string | undefined;
    onToggleFolder: (name: string, e: React.MouseEvent) => void;
    onLoadMore: (name: string, e: React.MouseEvent) => void;
    onDocClick: (doc: DocRecord) => void;
    searchQuery: string;
}

const ActualTree = ({
    treeData,
    expandedFolders,
    folderLimits,
    selectedDocId,
    onToggleFolder,
    onLoadMore,
    onDocClick,
    searchQuery
}: ActualTreeProps) => {
    if (treeData.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center py-12 text-slate-600 space-y-2 opacity-60">
                <Database size={24} />
                <span className="text-xs italic">No matching files found</span>
            </div>
        );
    }

    return (
        <div className="space-y-1">
            {treeData.map(node => (
                <TreeFolderItem 
                    key={node.folderName}
                    node={node}
                    isExpanded={expandedFolders.has(node.folderName)}
                    limit={folderLimits[node.folderName] || INITIAL_FOLDER_LIMIT}
                    selectedDocId={selectedDocId}
                    onToggle={onToggleFolder}
                    onLoadMore={onLoadMore}
                    onDocClick={onDocClick}
                />
            ))}
        </div>
    );
};

// --- MAIN COMPONENT ---

const OmniHubTab: React.FC = () => {
  const { 
    docs, concepts, addLog, securityState, reportSecurityEvent, 
    selectedDoc, setSelectedDoc, setActiveCenterId,
    expandedFolders, setExpandedFolders, folderLimits, setFolderLimits,
    treeSearchQuery, setTreeSearchQuery, actualTreeData, scrollToTreeItem,
    handleUpload, isUploading, uploadProgress
  } = useOmniHub();

  const [activeLeftTab, setActiveLeftTab] = useState<LeftTab>('chat');

  const [searchQuery, setSearchQuery] = useState('');
  const [ragResponse, setRagResponse] = useState<RagResponse | null>(null);
  const [viewModeState, setViewModeState] = useState<'default' | 'local' | 'evidence'>('default');
  const [evidenceData, setEvidenceData] = useState<{ docs: DocRecord[], concepts: ConceptNode[] } | null>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

  const [virtualFilters, setVirtualFilters] = useState<VirtualFilterState>({
      security: [], status: [], years: [], tags: []
  });

  const [recentSearches, setRecentSearches] = useState([
    "1분기 회계 감사", "2026 보안 규정", "신규 입사자 계약서", "프로젝트A 구매 요청", "컴플라이언스 준수 현황"
  ]);

  const handleLeftTabChange = useCallback((tab: LeftTab) => {
      setActiveLeftTab(tab);
      addLog(`LeftTab changed -> ${tab}`, 'INFO');
  }, [addLog]);

  const handleOpenSampleDoc = useCallback(() => {
    if (docs.length > 0) {
        const randomDoc = docs[Math.floor(Math.random() * 100)];
        setSelectedDoc(randomDoc);
        addLog(`문서 열람 -> ${randomDoc.name}`, 'INFO');
    }
  }, [docs, setSelectedDoc, addLog]);

  const handleDocSelect = useCallback((doc: DocRecord) => {
    if (activeLeftTab !== 'explorer') {
        setActiveLeftTab('explorer');
    }
    setSelectedDoc(doc);
    addLog(doc.ssotRating ? `증거 문서 열람 -> ${doc.name} (${doc.ssotRating.toUpperCase()})` : `문서 선택됨 -> ${doc.name}`, 'INFO');
  }, [activeLeftTab, setSelectedDoc, addLog]);

  // Sync Graph -> Tree
  useEffect(() => {
      if (!selectedDoc) return;
      // Use the robust scrolling mechanism from context
      scrollToTreeItem(selectedDoc.id, selectedDoc.actualPath);
  }, [selectedDoc, scrollToTreeItem]);

  // Auto-scroll chat
  useEffect(() => {
    if (activeLeftTab === 'chat' && ragResponse && chatScrollRef.current) {
        chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [ragResponse, activeLeftTab]);


  const toggleFolder = useCallback((folderName: string, e?: React.MouseEvent) => {
      if (e) {
          e.preventDefault();
          e.stopPropagation();
      }
      setExpandedFolders(prev => {
          const next = new Set(prev);
          if (next.has(folderName)) next.delete(folderName);
          else next.add(folderName);
          return next;
      });
      // Optionally initialize limits if not present
      setFolderLimits(prev => {
          if (!prev[folderName]) return { ...prev, [folderName]: INITIAL_FOLDER_LIMIT };
          return prev;
      });
  }, [setExpandedFolders, setFolderLimits]);

  const handleLoadMore = useCallback((folderName: string, e: React.MouseEvent) => {
      e.stopPropagation();
      setFolderLimits(prev => ({
          ...prev,
          [folderName]: (prev[folderName] || INITIAL_FOLDER_LIMIT) + LOAD_MORE_STEP
      }));
      addLog(`Tree load more -> ${folderName}`, 'INFO');
  }, [setFolderLimits, addLog]);

  const handleTreeDocClick = useCallback((doc: DocRecord) => {
      handleDocSelect(doc);
      setActiveCenterId(doc.id); 
  }, [handleDocSelect, setActiveCenterId]);

  const handleSearch = (query: string) => {
    if (!query.trim()) return;
    addLog(`검색 요청 -> ${query}`, 'INFO');
    reportSecurityEvent('APPROVE'); 
    setRecentSearches(prev => [query, ...prev.filter(s => s !== query)].slice(0, 5));
    setSearchQuery(''); // Clear input

    const keywords = query.toLowerCase().split(' ').filter(w => w.length > 1);
    const scoredDocs = docs.map(doc => {
        let score = 0;
        const lowerName = doc.name.toLowerCase();
        keywords.forEach(k => { if (lowerName.includes(k)) score += 10; });
        return { ...doc, _score: score + (Math.random() * 10) };
    });

    scoredDocs.sort((a, b) => b._score - a._score);
    const topDocs = scoredDocs.slice(0, 5);
    const evidenceDocs: DocRecord[] = topDocs.map((d, idx) => ({ ...d, ssotRating: idx === 0 ? 'gold' : 'silver' }));
    
    const relevantConceptIds = new Set<string>();
    evidenceDocs.forEach(d => d.conceptIds.forEach(id => relevantConceptIds.add(id)));
    const evidenceConcepts = concepts.filter(c => relevantConceptIds.has(c.id));

    // Simulate "Typing" or processing delay visually (though instant in logic)
    setRagResponse(null); // Clear previous temporarily to trigger animation if needed or just replace
    setTimeout(() => {
        setRagResponse({
            query: query,
            conclusion: `"${query}"에 대한 분석 결과, 가장 신뢰도 높은 문서는 '${topDocs[0].name}' 입니다.`,
            evidenceSummary: `근거 자료: '${topDocs[0].name}' (Gold 등급) 외 ${evidenceDocs.length - 1}건 식별됨.`,
            action: `권장 사항: 문서 소유자(${topDocs[0].owner})에게 최신 버전을 확인하세요.`
        });
        setEvidenceData({ docs: evidenceDocs, concepts: evidenceConcepts });
        setViewModeState('evidence');
    }, 50); // Slight tick for render cycle
  };

  return (
    <div className="flex flex-1 overflow-hidden relative">
      {/* Left Panel */}
      <div className="w-[380px] shrink-0 bg-[#0B0C15]/80 backdrop-blur-xl border-r border-cyan-500/10 flex flex-col z-10 shadow-[5px_0_30px_rgba(0,0,0,0.5)] relative transition-all">
        <div className="absolute top-0 right-0 w-px h-full bg-gradient-to-b from-transparent via-cyan-500/20 to-transparent"></div>

        {/* Tab Navigation */}
        <div className="px-4 pt-4 pb-2">
            <div className="flex bg-black/40 p-1 rounded-lg border border-white/5">
                <button 
                    onClick={() => handleLeftTabChange('chat')}
                    className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-xs font-bold transition-all ${
                        activeLeftTab === 'chat' 
                        ? 'bg-[#1e293b] text-white shadow-md border border-indigo-500/30 ring-1 ring-indigo-500/20' 
                        : 'text-slate-500 hover:text-slate-300 hover:bg-white/5'
                    }`}
                >
                    <Terminal size={14} className={activeLeftTab === 'chat' ? "text-indigo-400" : ""} /> AI Operator
                </button>
                <button 
                    onClick={() => handleLeftTabChange('explorer')}
                    className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-xs font-bold transition-all ${
                        activeLeftTab === 'explorer' 
                        ? 'bg-[#1e293b] text-white shadow-md border border-amber-500/30 ring-1 ring-amber-500/20' 
                        : 'text-slate-500 hover:text-slate-300 hover:bg-white/5'
                    }`}
                >
                    <FolderTree size={14} className={activeLeftTab === 'explorer' ? "text-amber-400" : ""} /> File Sys
                </button>
            </div>
        </div>

        {/* CHAT TAB CONTENT */}
        {activeLeftTab === 'chat' && (
          <>
            <div className="flex-1 p-4 overflow-y-auto flex flex-col scrollbar-thin scroll-smooth" ref={chatScrollRef}>
                <div className="mb-4 flex items-center justify-between text-indigo-400/80">
                    <div className="flex items-center gap-2">
                        <Sparkles size={14} className="animate-pulse" />
                        <h2 className="font-bold uppercase tracking-[0.2em] text-[9px]">Neural Link Established</h2>
                    </div>
                    <span className="text-[9px] font-mono opacity-50">v1.0.4</span>
                </div>

                {!ragResponse ? (
                    /* EMPTY STATE / STANDBY */
                    <div className="flex-1 flex flex-col items-center justify-center text-center space-y-8 animate-in fade-in zoom-in-95 duration-700">
                        <div className="relative group">
                            <div className="absolute inset-0 bg-indigo-500/20 blur-2xl rounded-full animate-pulse"></div>
                            <div className="w-32 h-32 bg-[#0f172a] rounded-full border-2 border-indigo-500/30 flex items-center justify-center relative z-10 shadow-[0_0_30px_rgba(99,102,241,0.1)] group-hover:border-indigo-400/60 transition-colors">
                                <Cpu className="text-indigo-400 animate-pulse" size={48} />
                                <div className="absolute inset-0 border border-indigo-500/10 rounded-full w-full h-full animate-[spin_10s_linear_infinite]"></div>
                                <div className="absolute inset-2 border border-indigo-500/10 rounded-full w-[88%] h-[88%] animate-[spin_15s_linear_infinite_reverse]"></div>
                            </div>
                        </div>
                        
                        <div className="space-y-2">
                            <h3 className="text-lg font-bold text-white tracking-widest uppercase">Core Online</h3>
                            <div className="flex items-center justify-center gap-2">
                                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                                <p className="text-xs text-slate-400 font-mono">Awaiting tactical command...</p>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 gap-2 w-full max-w-[240px]">
                            <button 
                                onClick={handleOpenSampleDoc}
                                className="px-4 py-3 bg-white/5 hover:bg-indigo-500/10 text-slate-300 hover:text-indigo-300 rounded border border-white/5 hover:border-indigo-500/30 transition-all flex items-center justify-center gap-2 text-xs font-bold"
                            >
                                <FileSearch size={14} /> Open Random Asset
                            </button>
                        </div>
                    </div>
                ) : (
                    /* RESULT STATE - CONVERSATION STYLE */
                    <div className="flex flex-col gap-6 pb-6">
                        
                        {/* 1. User Query (Right) */}
                        <div className="flex justify-end animate-in slide-in-from-right-10 fade-in duration-300">
                            <div className="max-w-[85%] bg-slate-800/80 backdrop-blur border border-slate-600/30 rounded-2xl rounded-tr-none p-4 shadow-lg">
                                <div className="flex items-center gap-2 mb-1 text-[9px] text-slate-400 uppercase font-bold tracking-wider">
                                    <Command size={10} /> Command Log
                                </div>
                                <p className="text-sm text-white font-medium leading-relaxed keep-all">
                                    {ragResponse.query}
                                </p>
                            </div>
                        </div>

                        {/* 2. AI Response (Left) */}
                        <div className="flex flex-col gap-2 animate-in slide-in-from-left-10 fade-in duration-500 delay-100">
                            
                            <div className="flex items-center gap-2 ml-1">
                                <Bot size={16} className="text-indigo-400" />
                                <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">Analysis Module</span>
                                <div className="h-px bg-indigo-900/50 flex-1"></div>
                            </div>

                            <div className="space-y-3">
                                {/* Conclusion Card */}
                                <div className="glass-panel p-4 rounded-xl border-l-4 border-l-indigo-500 shadow-[0_4px_20px_rgba(0,0,0,0.2)]">
                                    <div className="flex items-center gap-2 mb-2">
                                        <Terminal size={12} className="text-indigo-400" />
                                        <span className="text-indigo-100 font-bold text-[10px] uppercase tracking-wider">Executive Summary</span>
                                    </div>
                                    <p className="text-sm text-slate-200 leading-relaxed keep-all font-light">
                                        {ragResponse.conclusion}
                                    </p>
                                </div>

                                {/* Action Card */}
                                <div className="glass-panel p-4 rounded-xl border-l-4 border-l-emerald-500 bg-emerald-950/10">
                                    <div className="flex items-center gap-2 mb-2">
                                        <CheckCircle2 size={12} className="text-emerald-400" />
                                        <span className="text-emerald-100 font-bold text-[10px] uppercase tracking-wider">Recommended Action</span>
                                    </div>
                                    <p className="text-sm text-slate-200 leading-relaxed keep-all font-light">
                                        {ragResponse.action}
                                    </p>
                                </div>

                                {/* Evidence List */}
                                <div className="mt-2 bg-black/20 rounded-xl border border-white/5 overflow-hidden">
                                    <div className="px-4 py-2 bg-white/5 border-b border-white/5 flex items-center justify-between">
                                        <span className="text-[10px] font-bold text-slate-400 uppercase flex items-center gap-2">
                                            <Hash size={10} /> Reference Data ({evidenceData?.docs.length})
                                        </span>
                                    </div>
                                    <div className="divide-y divide-white/5">
                                        {evidenceData?.docs.map(doc => (
                                            <button 
                                                key={doc.id}
                                                onClick={() => handleDocSelect(doc)}
                                                className="w-full text-left px-4 py-3 hover:bg-indigo-500/10 transition-colors flex items-center gap-3 group"
                                            >
                                                <div className="shrink-0 text-slate-500 group-hover:text-indigo-400">
                                                    {doc.ssotRating === 'gold' ? <Star size={12} className="fill-amber-400 text-amber-400" /> : <FileText size={12} />}
                                                </div>
                                                <div className="min-w-0 flex-1">
                                                    <div className="text-xs text-slate-300 font-medium truncate group-hover:text-indigo-200 tracking-tight">{doc.name}</div>
                                                    <div className="flex gap-2 mt-0.5">
                                                        <span className="text-[9px] text-slate-600 font-mono">{doc.owner.split('@')[0]}</span>
                                                        {doc.ssotRating && <span className="text-[9px] text-amber-500 font-bold">SSOT</span>}
                                                    </div>
                                                </div>
                                                <ArrowRight size={12} className="text-indigo-500 opacity-0 group-hover:opacity-100 -translate-x-2 group-hover:translate-x-0 transition-all" />
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Recent Queries Overlay (Only show if at bottom and idle, or simple list at bottom) */}
                {!ragResponse && (
                    <div className="mt-auto pt-6 border-t border-white/5 animate-in fade-in slide-in-from-bottom-4 duration-700 delay-300">
                        <div className="flex items-center gap-2 text-[9px] font-bold text-slate-500 mb-3 uppercase tracking-widest">
                            <History size={10} /> Terminal History
                        </div>
                        <div className="space-y-1">
                            {recentSearches.map((item, idx) => (
                                <button 
                                    key={idx} 
                                    onClick={() => { setSearchQuery(item); handleSearch(item); }}
                                    className="w-full text-left group flex items-center justify-between px-3 py-2 rounded-lg hover:bg-white/5 transition-colors"
                                >
                                    <span className="text-xs text-slate-400 group-hover:text-indigo-200 truncate font-mono">{`> ${item}`}</span>
                                </button>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* Input Area */}
            <div className="p-4 border-t border-white/5 bg-[#0B0C15]/95 backdrop-blur z-20">
                <div className="relative group">
                    <input 
                        type="text" 
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSearch(searchQuery)}
                        placeholder="Enter system command or query..." 
                        className="w-full bg-[#151925] border border-white/10 text-slate-100 pl-10 pr-12 py-3 rounded-md focus:outline-none focus:border-indigo-500/50 focus:bg-[#1a1f2e] focus:shadow-[0_0_15px_rgba(99,102,241,0.1)] transition-all text-sm font-mono placeholder-slate-600 group-hover:border-white/20"
                    />
                    <div className="absolute left-3.5 top-3.5 flex items-center justify-center">
                        <span className="w-2 h-2 bg-indigo-500 rounded-sm animate-pulse"></span>
                    </div>
                    <button 
                        onClick={() => handleSearch(searchQuery)}
                        className="absolute right-2 top-2 bg-white/5 hover:bg-indigo-500 text-slate-400 hover:text-white p-1.5 rounded transition-all active:scale-95"
                    >
                        <ArrowRight size={16} />
                    </button>
                </div>
            </div>
          </>
        )}

        {/* EXPLORER TAB CONTENT - ACTUAL TREE */}
        {activeLeftTab === 'explorer' && (
             <div className="flex-1 flex flex-col h-full overflow-hidden">
                <div className="px-6 pt-6 pb-2 shrink-0">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2 text-amber-400">
                            <FolderTree size={16} />
                            <h2 className="font-bold uppercase tracking-wider text-xs">
                                Actual File System
                            </h2>
                        </div>
                    </div>
                    
                    {/* Tree Search Input */}
                    <div className="relative group mb-4">
                        <input 
                            type="text" 
                            value={treeSearchQuery}
                            onChange={(e) => setTreeSearchQuery(e.target.value)}
                            placeholder="Filter nodes..."
                            className="w-full bg-[#050508] border border-white/10 text-slate-200 pl-9 pr-4 py-2 rounded-md text-xs focus:outline-none focus:border-amber-500/50 transition-all placeholder-slate-600 font-mono"
                        />
                        <Filter className="absolute left-2.5 top-2.5 text-slate-500" size={12} />
                    </div>
                </div>
                
                <div className="flex-1 overflow-y-auto px-4 pb-6 scrollbar-thin">
                    <ActualTree 
                        treeData={actualTreeData}
                        expandedFolders={expandedFolders}
                        folderLimits={folderLimits}
                        selectedDocId={selectedDoc?.id}
                        onToggleFolder={toggleFolder}
                        onLoadMore={handleLoadMore}
                        onDocClick={handleTreeDocClick}
                        searchQuery={treeSearchQuery}
                    />
                </div>
                
                {/* Footer Info */}
                <div className="px-6 py-3 border-t border-white/5 bg-[#0e0e12] text-[10px] text-slate-500 flex justify-between items-center shrink-0">
                    <span className="flex items-center gap-1">
                        <Database size={10} /> 
                        <span className="text-slate-400">Total Nodes:</span> 
                        <span className="text-slate-200 font-mono">{docs.length}</span>
                    </span>
                    <span className="opacity-50 font-mono">SYS_READY</span>
                </div>
             </div>
        )}
      </div>

      {/* Right Panel: Graph */}
      <div className="flex-1 relative overflow-hidden flex flex-col">
        {/* Upload Button */}
        <div className="absolute top-6 right-6 z-10">
            {isUploading ? (
                <div className="flex items-center gap-4 bg-[#0f172a]/90 backdrop-blur-md px-5 py-3 rounded-lg border border-indigo-500/50 shadow-[0_0_20px_rgba(99,102,241,0.2)] min-w-[240px]">
                    <Loader2 size={20} className="text-indigo-400 animate-spin" />
                    <div className="flex-1">
                         <div className="flex justify-between text-xs font-bold text-indigo-200 mb-1.5 font-mono">
                            <span>UPLOADING_STREAM</span>
                            <span>{uploadProgress}%</span>
                         </div>
                         <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                             <div className="h-full bg-indigo-400 shadow-[0_0_10px_#818cf8] transition-all duration-150" style={{ width: `${uploadProgress}%` }}></div>
                         </div>
                    </div>
                </div>
            ) : (
                <button 
                    onClick={() => handleUpload()}
                    className="group flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white px-5 py-2.5 rounded-lg border border-violet-400/30 shadow-lg shadow-violet-600/20 text-sm font-bold transition-all hover:scale-105 active:scale-95"
                >
                    <CloudUpload size={18} className="group-hover:animate-bounce" />
                    <span className="tracking-wide">Ingest Data</span>
                </button>
            )}
        </div>

        {/* Graph Canvas */}
        <div className="flex-1 relative">
            <GraphVisualizer 
                viewModeState={viewModeState}
                evidenceData={evidenceData}
                virtualFilters={virtualFilters}
            />
            {selectedDoc && (
                <DocDetailDrawer />
            )}
        </div>
      </div>
    </div>
  );
};

export default OmniHubTab;