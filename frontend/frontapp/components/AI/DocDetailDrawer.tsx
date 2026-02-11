import React, { useState, useEffect } from 'react';
import { DocService, DocDetail } from '../../services/docService';
import { useOmniHub } from '../../context/OmniHubContext';
import { X, ChevronDown, ChevronRight, Download, ExternalLink, FolderInput, Shield, ShieldAlert, ShieldCheck, Clock, HardDrive, User, Star, BrainCircuit, Check, Ban, Lock, GitBranch, Network, FileText } from 'lucide-react';

// ========== Props Interface ==========
interface Props {
    docId: string;
    onClose: () => void;
}

// ========== [UI/UX] Collapsible Section Component ==========
const CollapsibleSection = ({
    title,
    isOpen,
    onToggle,
    children
}: {
    title: string;
    isOpen: boolean;
    onToggle: () => void;
    children?: React.ReactNode
}) => (
    <div className="border border-white/5 rounded-xl bg-white/5 overflow-hidden mb-3 transition-all duration-200 hover:border-white/10">
        <button
            onClick={onToggle}
            className="w-full flex items-center justify-between px-5 py-3 hover:bg-white/5 transition-colors"
        >
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wide">{title}</span>
            {isOpen ? <ChevronDown size={14} className="text-slate-400" /> : <ChevronRight size={14} className="text-slate-400" />}
        </button>
        {isOpen && (
            <div className="p-5 border-t border-white/5 animate-in fade-in slide-in-from-top-1 duration-200 bg-black/20">
                {children}
            </div>
        )}
    </div>
);

const DocDetailDrawer: React.FC<Props> = ({ docId, onClose }) => {
    const { addLog, reportSecurityEvent, updateDoc } = useOmniHub(); // securityState removed as requested

    // ========== State Management ==========
    const [doc, setDoc] = useState<DocDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [sections, setSections] = useState({
        summary: true,
        metadata: true,
        actions: true,
        concepts: true,
        evidence: true,
        ssot: true
    });

    const [rejectMode, setRejectMode] = useState(false);
    const [rejectReason, setRejectReason] = useState("");
    const [actionLoading, setActionLoading] = useState(false);

    // ========== Data Load ==========
    useEffect(() => {
        loadDoc();
    }, [docId]);

    const loadDoc = async () => {
        setLoading(true);
        try {
            const data = await DocService.getDocDetail(docId);
            setDoc(data);
        } catch (err) {
            console.error(err);
            setError("문서 정보를 불러오는데 실패했습니다.");
        } finally {
            setLoading(false);
        }
    };

    const toggleSection = (key: keyof typeof sections) => {
        setSections(prev => ({ ...prev, [key]: !prev[key] }));
    };

    // ========== [UI/UX] Security Badge Logic ==========
    const getSecurityBadge = (level?: string) => {
        switch (level?.toLowerCase()) {
            case 'high':
                return <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-red-500/10 border border-red-500/30 text-red-400 text-[10px] font-black uppercase tracking-wider shadow-[0_0_10px_rgba(239,68,68,0.2)]"><ShieldAlert size={12} /> HIGH SEC</div>;
            case 'medium':
                return <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] font-black uppercase tracking-wider shadow-[0_0_10px_rgba(245,158,11,0.2)]"><Shield size={12} /> MEDIUM SEC</div>;
            default:
                return <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[10px] font-black uppercase tracking-wider shadow-[0_0_10px_rgba(16,185,129,0.2)]"><ShieldCheck size={12} /> LOW SEC</div>;
        }
    };

    // ========== Action Handlers using DocService ==========
    const handleOpen = () => {
        if (doc?.source_link) {
            window.open(doc.source_link, '_blank');
            addLog(`문서 열기 -> ${doc.title}`, 'INFO');
        } else {
            addLog(`문서 열기 실패 (링크 없음) -> ${doc?.title}`, 'WARN');
        }
    };

    const handleDownload = async () => {
        try {
            setActionLoading(true);
            const result = await DocService.downloadDocument(docId);

            // A. Streaming Response (Blob)
            if (result.blob) {
                const url = window.URL.createObjectURL(result.blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = result.filename || (doc?.title ? `${doc.title}.pdf` : 'document.pdf');
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                reportSecurityEvent('DOWNLOAD');
                addLog(`다운로드 완료 (Stream) -> ${a.download}`, 'INFO', 'SECURITY');
            }
            // B. JSON Response (Fallback Link)
            else if (result.mime_type || result.url) { // Check for JSON fields
                if (result.method === 'webview') {
                    window.open(result.download_url || result.url, '_blank');
                } else {
                    const a = document.createElement('a');
                    a.href = result.download_url || result.url;
                    a.download = result.filename || 'document';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                }
                reportSecurityEvent('DOWNLOAD');
                addLog(`다운로드 링크 실행 -> ${doc?.title}`, 'INFO', 'SECURITY');
            } else {
                throw new Error("Unknown response format");
            }

        } catch (err: any) {
            console.error("Download Error:", err);

            let userMessage = '다운로드에 실패했습니다.';
            if (err.message && typeof err.message === 'string') {
                if (err.message.includes('404')) {
                    userMessage = '파일을 찾을 수 없습니다.';
                } else if (err.message.includes('401')) {
                    userMessage = '로그인이 필요합니다.';
                }
            }

            addLog(`다운로드 실패 -> ${userMessage}`, 'ERROR');
        } finally {
            setActionLoading(false);
        }
    };

    const handleApprove = async () => {
        try {
            setActionLoading(true);
            await DocService.updateDocStatus(docId, 'APPROVED');
            addLog(`문서 승인됨 -> ${doc?.title}`, 'INFO');

            updateDoc(docId, { status: 'approved' }); // Reflect in Context/Graph
            setDoc(prev => (prev ? { ...prev, review_status: 'APPROVED' } : null));
        } catch (err) {
            console.error("Approve Error:", err);
            addLog(`승인 실패 -> ${err}`, 'ERROR');
        } finally {
            setActionLoading(false);
        }
    };

    const handleRejectSubmit = async () => {
        if (!rejectReason.trim()) return;
        try {
            setActionLoading(true);
            await DocService.updateDocStatus(docId, 'REJECTED', rejectReason);
            addLog(`문서 반려됨 -> ${doc?.title}`, 'WARN');
            updateDoc(docId, { status: 'rejected' });
            setDoc(prev => (prev ? { ...prev, review_status: 'REJECTED' } : null));
            setRejectMode(false);
        } catch (err) {
            console.error("Reject Error:", err);
            addLog(`반려 실패 -> ${err}`, 'ERROR');
        } finally {
            setActionLoading(false);
        }
    };

    // ========== Rendering ==========
    if (loading) {
        return (
            <div className="absolute top-6 bottom-6 right-6 w-[420px] bg-[#09090b]/90 backdrop-blur-2xl border border-white/10 shadow-[0_0_50px_rgba(0,0,0,0.6)] z-40 flex flex-col items-center justify-center rounded-2xl">
                <div className="animate-spin w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full shadow-[0_0_15px_#6366f1]"></div>
            </div>
        );
    }

    if (error || !doc) {
        return (
            <div className="absolute top-6 bottom-6 right-6 w-[420px] bg-[#09090b]/90 backdrop-blur-2xl border border-white/10 shadow-[0_0_50px_rgba(0,0,0,0.6)] z-40 flex flex-col p-8 rounded-2xl">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-red-400 font-bold flex items-center gap-2"><ShieldAlert size={18} /> Error</h2>
                    <button onClick={onClose}><X size={20} className="text-slate-400 hover:text-white" /></button>
                </div>
                <p className="text-slate-300">{error || "Document not found"}</p>
            </div>
        );
    }

    const isPending = doc.review_status === 'PENDING';
    const isApproved = doc.review_status === 'APPROVED';
    const isRejected = doc.review_status === 'REJECTED';

    return (
        <div className="absolute top-6 bottom-6 right-6 w-[420px] bg-[#050508]/85 backdrop-blur-2xl border border-white/10 shadow-[0_0_60px_rgba(0,0,0,0.7)] z-40 flex flex-col rounded-2xl overflow-hidden ring-1 ring-white/5 animate-in slide-in-from-right-8 duration-500 group">

            {/* Holographic Effects */}
            <div className="absolute inset-0 pointer-events-none rounded-2xl border border-white/5 box-border"></div>
            <div className="absolute top-0 right-0 w-40 h-40 bg-indigo-500/10 blur-[60px] pointer-events-none rounded-full"></div>
            <div className="absolute bottom-0 left-0 w-32 h-32 bg-cyan-500/5 blur-[50px] pointer-events-none rounded-full"></div>

            {/* Header */}
            <div className="shrink-0 flex flex-col px-6 py-5 border-b border-white/10 bg-gradient-to-r from-white/5 to-transparent relative z-10">
                <button onClick={onClose} className="absolute top-4 right-4 p-2 hover:bg-white/10 rounded-full text-slate-400 hover:text-white transition-colors z-10">
                    <X size={20} />
                </button>

                <h2 className="text-xl font-bold text-white truncate pr-8 leading-tight mb-3 tracking-tight drop-shadow-md keep-all" title={doc.title}>{doc.title}</h2>

                <div className="flex flex-wrap items-center gap-2">
                    {getSecurityBadge(doc.policy?.security_level)}
                    {doc.policy?.ssot_level && (
                        <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${doc.policy.ssot_level === 'gold'
                            ? 'bg-amber-500/10 border-amber-500/30 text-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.2)]'
                            : 'bg-slate-500/10 border-slate-500/30 text-slate-400'
                            }`}>
                            <Star
                                size={10}
                                className={doc.policy.ssot_level === 'gold' ? "fill-amber-400" : "fill-slate-400"}
                            />
                            SSOT {doc.policy.ssot_level}
                        </div>
                    )}
                    {/* Status Badge */}
                    {isPending && <div className="px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/30 text-blue-400 text-[10px] font-bold uppercase flex items-center gap-1"><Clock size={10} /> PENDING REVIEW</div>}
                    {isApproved && <div className="px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[10px] font-bold uppercase flex items-center gap-1"><Check size={10} /> APPROVED</div>}
                    {isRejected && <div className="px-2 py-0.5 rounded bg-red-500/10 border border-red-500/30 text-red-400 text-[10px] font-bold uppercase flex items-center gap-1"><Ban size={10} /> REJECTED</div>}
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent relative z-10">

                {/* Pending Approval Action Card */}
                {isPending && (
                    <div className="mb-6 bg-gradient-to-br from-indigo-950/40 to-slate-900 border border-indigo-500/20 rounded-xl p-5 shadow-lg relative overflow-hidden group">
                        <div className="absolute inset-0 bg-indigo-500/5 animate-pulse pointer-events-none"></div>
                        <div className="absolute top-0 right-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
                            <BrainCircuit size={64} className="text-indigo-400" />
                        </div>

                        <div className="flex items-center gap-2 mb-4 relative z-10">
                            <div className="p-1.5 bg-indigo-600 rounded shadow-[0_0_10px_#4f46e5]">
                                <BrainCircuit size={16} className="text-white" />
                            </div>
                            <h3 className="text-sm font-bold text-indigo-100">AI Classification Proposal</h3>
                            <span className="ml-auto text-[9px] font-mono bg-indigo-500/20 text-indigo-300 px-2 py-1 rounded border border-indigo-500/30">
                                CONFIDENCE: 89%
                            </span>
                        </div>

                        <div className="space-y-3 text-xs text-slate-300 mb-5 bg-black/40 p-4 rounded-lg border border-white/5 relative z-10 font-mono">
                            <div className="flex justify-between items-center border-b border-white/5 pb-2">
                                <span className="text-slate-500 font-bold">PATH</span>
                                <span className="text-indigo-300 truncate max-w-[180px]">{doc.folder_path}</span>
                            </div>
                            <div className="flex justify-between items-center border-b border-white/5 pb-2">
                                <span className="text-slate-500 font-bold">SEC_LEVEL</span>
                                <span className="font-bold text-amber-400 uppercase tracking-wider">{doc.policy?.security_level}</span>
                            </div>
                        </div>

                        {!rejectMode ? (
                            <div className="grid grid-cols-2 gap-3 relative z-10">
                                <button
                                    onClick={handleApprove}
                                    disabled={actionLoading}
                                    className="flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold transition-all bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/20 active:scale-95 disabled:opacity-50 disabled:cursor-wait"
                                >
                                    {actionLoading ? <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Check size={16} />}
                                    APPROVE
                                </button>
                                <button
                                    onClick={() => setRejectMode(true)}
                                    disabled={actionLoading}
                                    className="flex items-center justify-center gap-2 py-2.5 bg-white/5 hover:bg-red-500/20 text-slate-300 hover:text-red-200 border border-white/10 hover:border-red-500/30 rounded-lg text-xs font-bold transition-all active:scale-95 disabled:opacity-50"
                                >
                                    <Ban size={16} /> REJECT
                                </button>
                            </div>
                        ) : (
                            <div className="space-y-3 animate-in fade-in relative z-10">
                                <textarea
                                    value={rejectReason}
                                    onChange={(e) => setRejectReason(e.target.value)}
                                    placeholder="Enter rejection reason..."
                                    className="w-full bg-[#050508] border border-red-500/30 rounded-lg p-3 text-xs text-slate-200 focus:border-red-500 focus:outline-none h-20 placeholder-slate-600 font-mono keep-all resize-none"
                                />
                                <div className="flex gap-2">
                                    <button
                                        onClick={handleRejectSubmit}
                                        disabled={actionLoading}
                                        className="flex-1 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-bold shadow-lg shadow-red-900/20 flex justify-center items-center gap-2"
                                    >
                                        {actionLoading && <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />}
                                        CONFIRM REJECT
                                    </button>
                                    <button
                                        onClick={() => setRejectMode(false)}
                                        className="px-4 py-2 bg-white/10 hover:bg-white/20 text-slate-300 rounded-lg text-xs font-bold"
                                    >
                                        CANCEL
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* SSOT Reliability Analysis */}
                {(doc.ssot_score !== undefined || doc.ssot_explain) && (
                    <CollapsibleSection
                        title="SSOT Reliability Analysis"
                        isOpen={sections.ssot}
                        onToggle={() => toggleSection('ssot')}
                    >
                        <div className="space-y-4">
                            {/* Score Gauge */}
                            <div className="flex items-center gap-4">
                                <div className="relative w-16 h-16">
                                    <svg className="w-16 h-16 -rotate-90" viewBox="0 0 36 36">
                                        <path
                                            className="text-slate-700"
                                            strokeDasharray="100, 100"
                                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                            fill="none"
                                            stroke="currentColor"
                                            strokeWidth="3"
                                        />
                                        <path
                                            className={`${(doc.ssot_score || 0) >= 70 ? 'text-emerald-500' : (doc.ssot_score || 0) >= 40 ? 'text-amber-500' : 'text-red-500'}`}
                                            strokeDasharray={`${doc.ssot_score || 0}, 100`}
                                            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                            fill="none"
                                            stroke="currentColor"
                                            strokeWidth="3"
                                            strokeLinecap="round"
                                        />
                                    </svg>
                                    <div className="absolute inset-0 flex items-center justify-center">
                                        <span className="text-lg font-bold text-white">{doc.ssot_score || 0}</span>
                                    </div>
                                </div>
                                <div className="flex-1">
                                    <div className="text-xs text-slate-400 uppercase tracking-wider mb-1">Reliability Score</div>
                                    <div className="text-sm text-slate-200 leading-relaxed">{doc.ssot_explain || 'No explanation available'}</div>
                                </div>
                            </div>

                            {/* Security Explanation */}
                            {doc.security_explain && (
                                <div className="p-3 bg-black/30 rounded-lg border border-white/5">
                                    <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1 flex items-center gap-1">
                                        <Shield size={10} /> Security Reason
                                    </div>
                                    <div className="text-xs text-slate-300">{doc.security_explain}</div>
                                </div>
                            )}

                            {/* Signal Breakdown */}
                            {doc.ssot_signals && doc.ssot_signals.length > 0 && (
                                <div className="space-y-2">
                                    <div className="text-[10px] text-slate-500 uppercase tracking-wider">Signal Breakdown</div>
                                    {doc.ssot_signals.slice(0, 5).map((sig, i) => (
                                        <div key={i} className="flex items-center justify-between text-xs p-2 bg-black/20 rounded border border-white/5">
                                            <span className="text-slate-400 truncate max-w-[200px]">{sig.evidence}</span>
                                            <span className={`font-mono font-bold ${sig.delta > 0 ? 'text-emerald-400' : sig.delta < 0 ? 'text-red-400' : 'text-slate-500'}`}>
                                                {sig.delta > 0 ? '+' : ''}{sig.delta}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </CollapsibleSection>
                )}

                {/* 1. AI Summary */}
                {(doc.card?.l1 || doc.card?.l2) && (
                    <CollapsibleSection
                        title="AI Executive Summary"
                        isOpen={sections.summary}
                        onToggle={() => toggleSection('summary')}
                    >
                        <ul className="space-y-4">
                            {/* L1 Summary */}
                            {doc.card?.l1 && (
                                <li className="flex gap-4 text-sm text-slate-300 leading-relaxed group">
                                    <div className="shrink-0 w-1.5 h-1.5 rounded-full bg-cyan-500 mt-2 group-hover:shadow-[0_0_8px_#22d3ee] transition-all"></div>
                                    <span className="opacity-90 keep-all font-light">{doc.card.l1}</span>
                                </li>
                            )}
                            {/* L2 Summary (Split by newlines) */}
                            {doc.card?.l2 && doc.card.l2.split('\n').filter(Boolean).map((line, idx) => (
                                <li key={idx} className="flex gap-4 text-sm text-slate-300 leading-relaxed group">
                                    <div className="shrink-0 w-1.5 h-1.5 rounded-full bg-cyan-500 mt-2 group-hover:shadow-[0_0_8px_#22d3ee] transition-all"></div>
                                    <span className="opacity-90 keep-all font-light">{line.replace(/^- /, '')}</span>
                                </li>
                            ))}
                            {/* L3 Summary (Detailed Context) */}
                            {doc.card?.l3 && (
                                <li className="flex gap-4 text-xs text-slate-400 leading-relaxed group mt-2 pt-2 border-t border-white/5">
                                    <div className="shrink-0 w-1.5 h-1.5 rounded-full bg-indigo-500 mt-1.5 group-hover:shadow-[0_0_8px_#6366f1] transition-all"></div>
                                    <span className="opacity-80 keep-all font-light italic">{doc.card.l3}</span>
                                </li>
                            )}
                        </ul>
                    </CollapsibleSection>
                )}

                {/* 2. Metadata */}
                <CollapsibleSection
                    title="File Metadata"
                    isOpen={sections.metadata}
                    onToggle={() => toggleSection('metadata')}
                >
                    <div className="grid grid-cols-2 gap-y-4 gap-x-3 text-xs">
                        <div className="space-y-1">
                            <div className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-wider text-[10px]"><Clock size={12} /> Updated</div>
                            <div className="text-slate-200 font-mono text-[11px] tracking-wide">
                                {doc.modified_time ? new Date(doc.modified_time).toLocaleDateString() : 'Unknown'}
                            </div>
                        </div>
                        <div className="col-span-2 space-y-1">
                            <div className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-wider text-[10px]"><FolderInput size={12} /> Path</div>
                            <div className="text-slate-400 font-mono text-[10px] break-all bg-black/20 p-2.5 rounded border border-white/5">
                                {doc.folder_path || 'Unknown'}
                            </div>
                        </div>
                    </div>
                </CollapsibleSection>

                {/* 3. Actions */}
                <CollapsibleSection
                    title="Quick Actions"
                    isOpen={sections.actions}
                    onToggle={() => toggleSection('actions')}
                >
                    <div className="grid grid-cols-2 gap-3">
                        <button
                            onClick={handleOpen}
                            disabled={!doc.source_link}
                            className={`flex flex-col items-center justify-center p-4 rounded-xl border transition-all gap-2 group ${!doc.source_link
                                ? 'bg-black/20 border-white/5 text-slate-600 cursor-not-allowed'
                                : 'bg-white/5 hover:bg-cyan-500/10 border-white/5 hover:border-cyan-500/30 text-slate-300 hover:text-cyan-300 shadow-lg shadow-cyan-900/10'
                                }`}
                        >
                            <ExternalLink size={20} className={!doc.source_link ? "text-slate-600" : "text-slate-400 group-hover:text-cyan-400 transition-colors"} />
                            <span className="text-[10px] font-bold uppercase tracking-wide">Open Source</span>
                        </button>
                        <button
                            onClick={handleDownload}
                            disabled={actionLoading}
                            className={`flex flex-col items-center justify-center p-4 rounded-xl border transition-all gap-2 group ${actionLoading
                                ? 'bg-black/20 border-white/5 text-slate-600 cursor-wait'
                                : 'bg-white/5 hover:bg-emerald-500/10 border-white/5 hover:border-emerald-500/30 text-slate-300 hover:text-emerald-300 shadow-lg shadow-emerald-900/10'
                                }`}
                        >
                            {actionLoading ? <div className="w-5 h-5 border-2 border-slate-500/30 border-t-slate-300 rounded-full animate-spin" /> :
                                <Download size={20} className="text-slate-400 group-hover:text-emerald-400 transition-colors" />}
                            <span className="text-[10px] font-bold uppercase tracking-wide">Download</span>
                        </button>
                    </div>
                </CollapsibleSection>

                {/* 4. Concepts */}
                {doc.concepts && doc.concepts.length > 0 && (
                    <CollapsibleSection
                        title="Related Concepts"
                        isOpen={sections.concepts}
                        onToggle={() => toggleSection('concepts')}
                    >
                        <div className="flex flex-wrap gap-2">
                            {doc.concepts.map((c: any, i) => {
                                const label = typeof c === 'string' ? c : (c.label || c.name || c.concept_id || "Unknown");
                                return (
                                    <span key={i} className="px-2.5 py-1 bg-indigo-500/10 hover:bg-indigo-500/20 rounded-md text-[10px] text-indigo-300 border border-indigo-500/20 transition-colors cursor-default flex items-center gap-1.5 font-mono">
                                        <Network size={10} />
                                        {label}
                                    </span>
                                );
                            })}
                        </div>
                    </CollapsibleSection>
                )}

                {/* 5. Evidence */}
                {doc.evidence && doc.evidence.length > 0 && (
                    <CollapsibleSection
                        title="Source Evidence"
                        isOpen={sections.evidence}
                        onToggle={() => toggleSection('evidence')}
                    >
                        <div className="space-y-3">
                            {doc.evidence.map((ev, i) => (
                                <div key={i} className="p-3 bg-black/30 rounded-lg border-l-2 border-amber-500/50 hover:bg-black/50 transition-colors">
                                    <div className="flex items-start gap-2 mb-1">
                                        <FileText size={12} className="text-slate-500 mt-0.5 shrink-0" />
                                        <p className="text-slate-300 text-[11px] italic leading-relaxed">"{ev.snippet}"</p>
                                    </div>
                                    <div className="mt-1 text-[9px] text-slate-500 text-right font-mono">Page {ev.page}</div>
                                </div>
                            ))}
                        </div>
                    </CollapsibleSection>
                )}

            </div>
        </div>
    );
};

export default DocDetailDrawer;