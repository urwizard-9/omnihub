
import React, { useState, useEffect, useRef } from 'react';
import { AIService } from '../../services/aiService';
import { useOmniHub } from '../../context/OmniHubContext';
import { RAGResponse, Citation, DocRecord } from '../../types';
import {
    Search, Loader2, Sparkles, Bot, Command,
    Terminal, CheckCircle2, AlertTriangle, Hash,
    ArrowRight, Star, FileText, Cpu, History, ExternalLink
} from 'lucide-react';

interface Props {
    onCitationClick: (docId: string) => void;
}

interface ParsedResponse {
    conclusion: string;
    basis: string;
    risk: string;
}

const RAGSearchPanel: React.FC<Props> = ({ onCitationClick }) => {
    const { docs, addLog, reportSecurityEvent } = useOmniHub();
    const [query, setQuery] = useState('');
    const [loading, setLoading] = useState(false);
    const [ragResponse, setRagResponse] = useState<RAGResponse | null>(null);
    const [parsedData, setParsedData] = useState<ParsedResponse | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [lastQuery, setLastQuery] = useState('');

    const chatScrollRef = useRef<HTMLDivElement>(null);

    // --- Auto Scroll ---
    useEffect(() => {
        if (ragResponse && chatScrollRef.current) {
            scrollToBottom();
        }
    }, [ragResponse]);

    const scrollToBottom = () => {
        if (chatScrollRef.current) {
            chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
        }
    }

    // --- Parser Logic ---
    const parseAnswer = (text: string): ParsedResponse => {
        // Default values
        let conclusion = "요약 정보를 추출할 수 없습니다.";
        let basis = "상세 근거를 추출할 수 없습니다.";
        let risk = "특이 사항 없음.";

        try {
            // Regex to extract sections based on hashtags
            // ## 1) 요약 결론
            // ## 2) 상세 판단 근거
            // ## 3) 리스크/확인 필요 사항
            // ## 4) References (Ignore text, use citations array)

            const conclusionMatch = text.match(/##\s*1\)\s*요약 결론\s*([\s\S]*?)(?=##\s*2\))/i);
            const basisMatch = text.match(/##\s*2\)\s*상세 판단 근거\s*([\s\S]*?)(?=##\s*3\))/i);
            const riskMatch = text.match(/##\s*3\)\s*리스크\/확인 필요 사항\s*([\s\S]*?)(?=##\s*4\)|$)/i);

            if (conclusionMatch && conclusionMatch[1]) conclusion = conclusionMatch[1].trim();
            if (basisMatch && basisMatch[1]) basis = basisMatch[1].trim();
            if (riskMatch && riskMatch[1]) risk = riskMatch[1].trim();

            // Fallback: If regex fails completely (e.g. model didn't follow format), use full text as conclusion
            if (!conclusionMatch && !basisMatch && !riskMatch) {
                conclusion = text;
                basis = "";
                risk = "";
            }

        } catch (e) {
            console.error("Parsing failed", e);
            conclusion = text;
        }

        return { conclusion, basis, risk };
    };

    const handleSearch = async (targetQuery: string) => {
        if (!targetQuery.trim()) return;

        setLoading(true);
        setError(null);
        setRagResponse(null);
        setParsedData(null);
        setLastQuery(targetQuery); // Save for display
        addLog(`검색 요청 -> ${targetQuery}`, 'INFO');
        reportSecurityEvent('APPROVE');

        try {
            const data = await AIService.searchRAG(targetQuery);
            setRagResponse(data);
            setParsedData(parseAnswer(data.answer));
        } catch (err: any) {
            setError(err.message || "Search failed");
            addLog(`검색 실패: ${err.message}`, 'ERROR');
        } finally {
            setLoading(false);
            setQuery(''); // Clear input for next
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSearch(query);
        }
    };

    // --- Reference Card Helpers ---
    const getDocMetadata = (docId: string, cit: Citation) => {
        const found = docs.find(d => d.id === docId);

        // Prefer API citation data if available (Phase 5 Update)
        const ssotScore = cit.ssot_score ?? (found?.ssotRating === 'gold' ? 90 : found?.ssotRating === 'silver' ? 70 : 50);
        const ssotExplain = cit.ssot_explain;

        return {
            owner: found ? found.owner.split('@')[0] : 'System',
            isSSOT: ssotScore >= 80, // Gold equivalent
            ssotScore,
            ssotExplain
        };
    };

    return (
        <div className="flex flex-col h-full bg-[#1E1F2E] border-l border-white/5 relative">
            {/* Header ... */}
            <div className="absolute top-0 left-0 w-full px-4 py-3 z-20 flex items-center justify-between text-indigo-400/80 bg-[#1E1F2E]/80 backdrop-blur-sm border-b border-indigo-500/10">
                <div className="flex items-center gap-2">
                    <Sparkles size={14} className="animate-pulse" />
                    <h2 className="font-bold uppercase tracking-[0.2em] text-[9px]">Neural Link Established</h2>
                </div>
                <span className="text-[9px] font-mono opacity-50">v2.1.0/RAG</span>
            </div>

            {/* Main Content Area */}
            <div className="flex-1 p-4 overflow-y-auto flex flex-col scrollbar-thin scrollbar-thumb-white/10 pt-12" ref={chatScrollRef}>

                {loading && (
                    <div className="flex-1 flex flex-col items-center justify-center space-y-4 animate-in fade-in duration-500">
                        <div className="relative">
                            <div className="w-16 h-16 border-2 border-indigo-500/30 border-t-indigo-500 rounded-full animate-spin"></div>
                            <div className="absolute inset-0 flex items-center justify-center">
                                <Cpu size={24} className="text-indigo-400 animate-pulse" />
                            </div>
                        </div>
                        <span className="text-xs font-mono text-indigo-300 animate-pulse">Processing Query...</span>
                    </div>
                )}

                {!ragResponse && !loading && !error && (
                    /* EMPTY STATE */
                    <div className="flex-1 flex flex-col items-center justify-center text-center space-y-8 animate-in fade-in zoom-in-95 duration-700 opacity-80">
                        <div className="relative group">
                            <div className="absolute inset-0 bg-indigo-500/20 blur-2xl rounded-full animate-pulse"></div>
                            <div className="w-32 h-32 bg-[#0f172a] rounded-full border-2 border-indigo-500/30 flex items-center justify-center relative z-10 shadow-[0_0_30px_rgba(99,102,241,0.1)] group-hover:border-indigo-400/60 transition-colors">
                                <Cpu className="text-indigo-400 animate-pulse" size={48} />
                            </div>
                        </div>
                        <div className="space-y-2">
                            <h3 className="text-lg font-bold text-white tracking-widest uppercase">Core Online</h3>
                            <p className="text-xs text-slate-400 font-mono">System Ready. Awaiting command...</p>
                        </div>
                    </div>
                )}

                {error && (
                    <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm mt-auto mb-4 animate-in slide-in-from-bottom-2">
                        <div className="flex items-center gap-2 mb-2 font-bold uppercase text-[10px]">
                            <AlertTriangle size={12} /> Error
                        </div>
                        {error}
                    </div>
                )}

                {ragResponse && parsedData && !loading && (
                    <div className="flex flex-col gap-6 pb-6 mt-4">
                        {/* 1. User Query Log */}
                        <div className="flex justify-end animate-in slide-in-from-right-10 fade-in duration-300">
                            <div className="max-w-[85%] bg-slate-800/80 backdrop-blur border border-slate-600/30 rounded-2xl rounded-tr-none p-4 shadow-lg">
                                <div className="flex items-center gap-2 mb-1 text-[9px] text-slate-400 uppercase font-bold tracking-wider">
                                    <Command size={10} /> QUERY LOG
                                </div>
                                <p className="text-sm text-white font-medium leading-relaxed keep-all">
                                    {lastQuery}
                                </p>
                            </div>
                        </div>

                        {/* 2. AI Response Cards */}
                        <div className="flex flex-col gap-2 animate-in slide-in-from-left-10 fade-in duration-500 delay-100">
                            <div className="flex items-center gap-2 ml-1">
                                <Bot size={16} className="text-indigo-400" />
                                <span className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">Analysis Module</span>
                                <div className="h-px bg-indigo-900/50 flex-1"></div>
                            </div>

                            {/* Summary Card */}
                            <div className="glass-panel p-4 rounded-xl border-l-4 border-l-indigo-500 shadow-[0_4px_20px_rgba(0,0,0,0.2)] bg-[#1e293b]/50">
                                <p className="text-sm text-slate-200 leading-relaxed keep-all font-light whitespace-pre-wrap">{parsedData.conclusion}</p>
                            </div>

                            {/* Basis Card */}
                            {parsedData.basis && (
                                <div className="glass-panel p-4 rounded-xl border-l-4 border-l-amber-500 bg-amber-950/10">
                                    <div className="text-sm text-slate-200 leading-relaxed keep-all font-light whitespace-pre-wrap">{parsedData.basis}</div>
                                </div>
                            )}

                            {/* Risk Card */}
                            {parsedData.risk && (
                                <div className="glass-panel p-4 rounded-xl border-l-4 border-l-red-500 bg-red-950/10">
                                    <div className="text-sm text-slate-200 leading-relaxed keep-all font-light whitespace-pre-wrap">{parsedData.risk}</div>
                                </div>
                            )}

                            {/* Reference Data with SSOT */}
                            {ragResponse.citations.length > 0 && (
                                <div className="mt-2 bg-[#0B0C15]/50 rounded-xl border border-white/5 overflow-hidden">
                                    <div className="px-4 py-2 bg-white/5 border-b border-white/5 flex items-center justify-between">
                                        <span className="text-[10px] font-bold text-slate-400 uppercase flex items-center gap-2">
                                            <Hash size={10} /> Reference Data ({ragResponse.citations.length})
                                        </span>
                                    </div>
                                    <div className="divide-y divide-white/5">
                                        {ragResponse.citations.map((cit) => {
                                            const meta = getDocMetadata(cit.doc_id, cit); // Pass cit
                                            return (
                                                <button
                                                    key={cit.idx}
                                                    onClick={() => onCitationClick(cit.doc_id)}
                                                    className="w-full text-left px-4 py-3 hover:bg-indigo-500/10 transition-colors flex items-center gap-3 group relative overflow-hidden"
                                                >
                                                    {/* SSOT Glow if High Score */}
                                                    {meta.ssotScore >= 80 && (
                                                        <div className="absolute left-0 top-0 bottom-0 w-1 bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.5)]"></div>
                                                    )}

                                                    <div className="shrink-0 text-slate-500 group-hover:text-indigo-400 mt-0.5">
                                                        {meta.ssotScore >= 80 ?
                                                            <Star size={14} className="fill-amber-400 text-amber-400" /> :
                                                            <FileText size={14} />
                                                        }
                                                    </div>
                                                    <div className="min-w-0 flex-1">
                                                        <div className="flex items-start justify-between">
                                                            <div className="text-xs text-slate-300 font-bold truncate group-hover:text-indigo-200 tracking-tight mb-0.5">
                                                                {cit.title || "Untitled Document"}
                                                            </div>
                                                            {cit.source_link && (
                                                                <a
                                                                    href={cit.source_link}
                                                                    target="_blank" rel="noreferrer"
                                                                    onClick={(e) => e.stopPropagation()}
                                                                    className="text-[10px] text-slate-600 hover:text-indigo-400 ml-2"
                                                                >
                                                                    <ExternalLink size={10} />
                                                                </a>
                                                            )}
                                                        </div>
                                                        <div className="flex gap-2 items-center flex-wrap">
                                                            <span className="text-[10px] text-slate-500 font-mono">Page {cit.page || '?'}</span>
                                                            <span className="text-[9px] text-slate-600">|</span>
                                                            <span className="text-[10px] text-slate-500 font-mono">{meta.owner}</span>

                                                            {/* SSOT Score Badge */}
                                                            {meta.ssotScore > 0 && (
                                                                <div className={`flex items-center gap-1 px-1.5 py-0.5 rounded ${meta.ssotScore >= 80 ? 'bg-amber-500/20 text-amber-300' : 'bg-slate-700/50 text-slate-400'}`}>
                                                                    <span className="text-[9px] font-bold">SSOT {meta.ssotScore}</span>
                                                                </div>
                                                            )}
                                                        </div>

                                                        {/* Snippet Preview */}
                                                        {cit.snippet && (
                                                            <div className="mt-1 text-[10px] text-slate-600 line-clamp-1 italic">
                                                                "{cit.snippet}"
                                                            </div>
                                                        )}

                                                        {/* SSOT Explanation (If present) */}
                                                        {meta.ssotExplain && (
                                                            <div className="mt-1 text-[9px] text-emerald-400/80 line-clamp-1">
                                                                💡 {meta.ssotExplain}
                                                            </div>
                                                        )}
                                                    </div>
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}

            </div>
            {/* Input Area ... */}
            <div className="p-4 border-t border-white/5 bg-[#0B0C15]/95 backdrop-blur z-20">
                <div className="relative group">
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Enter system command or query..."
                        disabled={loading}
                        className="w-full bg-[#151925] border border-white/10 text-slate-100 pl-10 pr-12 py-3 rounded-md focus:outline-none focus:border-indigo-500/50 focus:bg-[#1a1f2e] focus:shadow-[0_0_15px_rgba(99,102,241,0.1)] transition-all text-sm font-mono placeholder-slate-600 group-hover:border-white/20 disabled:opacity-50"
                    />
                    <div className="absolute left-3.5 top-3.5 flex items-center justify-center">
                        <span className={`w-2 h-2 bg-indigo-500 rounded-sm ${loading ? 'animate-spin' : 'animate-pulse'}`}></span>
                    </div>
                    <button
                        onClick={() => handleSearch(query)}
                        disabled={loading || !query.trim()}
                        className="absolute right-2 top-2 bg-white/5 hover:bg-indigo-500 text-slate-400 hover:text-white p-1.5 rounded transition-all active:scale-95 disabled:opacity-50 disabled:active:scale-100"
                    >
                        <ArrowRight size={16} />
                    </button>
                </div>
            </div>
        </div>
    );
};

export default RAGSearchPanel;

