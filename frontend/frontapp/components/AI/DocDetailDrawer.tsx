import React, { useState, useEffect } from 'react';
import { AIService } from '../../services/aiService';
import { DocCard } from '../../types';
import { useOmniHub } from '../../context/OmniHubContext';
import { X, ChevronDown, ChevronRight, Download, ExternalLink, FolderInput, Shield, ShieldAlert, ShieldCheck, Clock, HardDrive, User, Star, BrainCircuit, Check, Ban, Lock, GitBranch, Network, FileText } from 'lucide-react';

/**
 * [DocDetailDrawer]
 * 문서 상세 정보 패널입니다.
 * - AIService를 통해 문서 정보(DocCard)를 조회합니다.
 * - 메타데이터, AI 요약, 보안 등급, 관련 개념 등을 표시합니다.
 * - 파일 열기, 다운로드 등의 액션을 제공합니다.
 */

// ========== Props 인터페이스 ==========
interface Props {
    docId: string;        // 표시할 문서 ID
    onClose: () => void;  // 닫기 콜백
}

// ========== [UI/UX] Collapsible Section 컴포넌트 ==========
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
    // [UI/UX] 섹션 컨테이너: 아코디언 스타일
    <div className="border border-white/5 rounded-xl bg-white/5 overflow-hidden mb-3 transition-all duration-200">
        <button
            onClick={onToggle}
            className="w-full flex items-center justify-between px-5 py-3 hover:bg-white/5 transition-colors"
        >
            <span className="text-sm font-bold text-slate-200">{title}</span>
            {isOpen ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
        </button>
        {isOpen && (
            <div className="p-5 border-t border-white/5 animate-in fade-in slide-in-from-top-1 duration-200 bg-black/10">
                {children}
            </div>
        )}
    </div>
);

const DocDetailDrawer: React.FC<Props> = ({ docId, onClose }) => {
    const { addLog, securityState, reportSecurityEvent } = useOmniHub();

    // ========== 상태 관리 ==========
    const [doc, setDoc] = useState<DocCard | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [sections, setSections] = useState({
        summary: true,
        metadata: true,
        actions: true,
        concepts: true,
        evidence: false
    });

    // ========== 데이터 로드 ==========
    useEffect(() => {
        loadDoc();
    }, [docId]);

    const loadDoc = async () => {
        setLoading(true);
        try {
            const data = await AIService.getDocCard(docId);
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

    // ========== [UI/UX] 보안 뱃지 렌더링 ==========
    const getSecurityBadge = (level?: string) => {
        switch (level?.toLowerCase()) {
            case 'high':
                return <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-red-500/10 border border-red-500/30 text-red-400 text-[10px] font-black uppercase tracking-wider shadow-sm"><ShieldAlert size={12} /> HIGH SEC</div>;
            case 'medium':
                return <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] font-black uppercase tracking-wider shadow-sm"><Shield size={12} /> MEDIUM SEC</div>;
            default:
                return <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[10px] font-black uppercase tracking-wider shadow-sm"><ShieldCheck size={12} /> NORMAL SEC</div>;
        }
    };

    // ========== 액션 핸들러 ==========
    const handleOpen = () => {
        if (securityState.softBlocked) {
            reportSecurityEvent('BLOCK_ATTEMPT');
            addLog('보안 정책에 의해 문서 열람 차단됨', 'WARN', 'SECURITY');
            return;
        }

        if (doc?.source_link) {
            window.open(doc.source_link, '_blank');
            addLog(`문서 열기 -> ${doc.title}`, 'INFO');
        } else {
            addLog(`문서 열기 실패 (링크 없음) -> ${doc?.title}`, 'WARN');
        }
    };

    const handleDownload = () => {
        if (securityState.softBlocked) {
            reportSecurityEvent('BLOCK_ATTEMPT');
            addLog(`보안 정책에 의해 다운로드 차단됨`, 'WARN', 'SECURITY');
            return;
        }
        if (doc?.source_link) {
            window.open(doc.source_link, '_blank'); // 임시: 원문 링크로 이동
            reportSecurityEvent('DOWNLOAD');
            addLog(`다운로드 실행됨 -> ${doc.title}`, 'INFO', 'SECURITY');
        }
    };

    // ========== 렌더링: 로딩/에러 ==========
    if (loading) {
        return (
            <div className="absolute top-4 bottom-4 right-4 w-[420px] bg-[#09090b]/95 backdrop-blur-xl border border-white/10 shadow-2xl z-40 flex flex-col items-center justify-center rounded-2xl">
                <div className="animate-spin w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    if (error || !doc) {
        return (
            <div className="absolute top-4 bottom-4 right-4 w-[420px] bg-[#09090b]/95 backdrop-blur-xl border border-white/10 shadow-2xl z-40 flex flex-col p-6 rounded-2xl">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-red-400 font-bold">Error</h2>
                    <button onClick={onClose}><X size={20} className="text-slate-400" /></button>
                </div>
                <p className="text-slate-300">{error || "Document not found"}</p>
            </div>
        );
    }

    // ========== [UI/UX] 메인 렌더링 ==========
    return (
        // [UI/UX] 패널 컨테이너: 우측 슬라이드 애니메이션
        <div className="absolute top-4 bottom-4 right-4 w-[420px] bg-[#09090b]/95 backdrop-blur-xl border border-white/10 shadow-2xl z-40 flex flex-col rounded-2xl overflow-hidden ring-1 ring-white/5 animate-in slide-in-from-right-4 duration-300">

            {/* [UI/UX] Header: 제목 및 상단 정보 */}
            <div className="shrink-0 flex flex-col px-6 py-4 border-b border-white/10 bg-gradient-to-r from-white/5 to-transparent relative">
                <button onClick={onClose} className="absolute top-4 right-4 p-2 hover:bg-white/10 rounded-full text-slate-400 hover:text-white transition-colors z-10">
                    <X size={20} />
                </button>

                <h2 className="text-lg font-bold text-white truncate pr-8 leading-tight mb-3" title={doc.title}>{doc.title}</h2>

                <div className="flex flex-wrap items-center gap-2">
                    {getSecurityBadge(doc.policy?.security_level)}
                    {/* 추가 메타데이터가 있다면 여기에 표시 */}
                </div>
            </div>

            {/* [UI/UX] Content: 스크롤 영역 */}
            <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-white/10">

                {/* 1. AI Insight (Card L1/L2) */}
                {(doc.card?.l1 || doc.card?.l2) && (
                    <CollapsibleSection
                        title="AI Insight"
                        isOpen={sections.summary}
                        onToggle={() => toggleSection('summary')}
                    >
                        <div className="space-y-4">
                            {doc.card?.l1 && (
                                <div>
                                    <span className="text-indigo-400 text-[10px] font-bold mb-1.5 block uppercase tracking-wider">Executive Summary</span>
                                    <p className="text-lg font-medium text-white leading-snug">{doc.card.l1}</p>
                                </div>
                            )}
                            {doc.card?.l1 && doc.card?.l2 && <div className="h-px bg-white/10 w-full" />}
                            {doc.card?.l2 && (
                                <div>
                                    <span className="text-purple-400 text-[10px] font-bold mb-1.5 block uppercase tracking-wider">Key Details</span>
                                    <p className="text-slate-300 text-sm leading-relaxed whitespace-pre-line">{doc.card.l2}</p>
                                </div>
                            )}
                        </div>
                    </CollapsibleSection>
                )}

                {/* 2. Concepts (Tags) */}
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
                                    <span key={i} className="px-2.5 py-1 bg-indigo-500/10 hover:bg-indigo-500/20 rounded-md text-xs text-indigo-300 border border-indigo-500/20 transition-colors cursor-default flex items-center gap-1.5">
                                        <Network size={10} />
                                        {label}
                                    </span>
                                );
                            })}
                        </div>
                    </CollapsibleSection>
                )}

                {/* 3. Evidence */}
                {doc.evidence && doc.evidence.length > 0 && (
                    <CollapsibleSection
                        title="Source Evidence"
                        isOpen={sections.evidence}
                        onToggle={() => toggleSection('evidence')}
                    >
                        <div className="space-y-3">
                            {doc.evidence.map((ev, i) => (
                                <div key={i} className="p-3 bg-black/30 rounded-lg border-l-2 border-amber-500/50">
                                    <p className="text-slate-300 text-xs italic leading-relaxed">"{ev.snippet}"</p>
                                    <div className="mt-1 text-[10px] text-slate-500 text-right">Page {ev.page}</div>
                                </div>
                            ))}
                        </div>
                    </CollapsibleSection>
                )}

                {/* 4. Metadata */}
                <CollapsibleSection
                    title="File Metadata"
                    isOpen={sections.metadata}
                    onToggle={() => toggleSection('metadata')}
                >
                    <div className="grid grid-cols-1 gap-y-3 text-xs">
                        <div className="space-y-1">
                            <div className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-wider"><Clock size={12} /> Last Modified</div>
                            <div className="text-slate-200 font-mono pl-4">
                                {doc.modified_time ? new Date(doc.modified_time).toLocaleDateString() : 'Unknown'}
                            </div>
                        </div>
                        <div className="space-y-1">
                            <div className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-wider"><FolderInput size={12} /> Path</div>
                            <div className="text-slate-400 font-mono text-[10px] break-all bg-black/20 p-2.5 rounded border border-white/5">
                                {doc.folder_path || 'Unknown'}
                            </div>
                        </div>
                    </div>
                </CollapsibleSection>

                {/* 5. Actions */}
                <CollapsibleSection
                    title="Quick Actions"
                    isOpen={sections.actions}
                    onToggle={() => toggleSection('actions')}
                >
                    <div className="grid grid-cols-2 gap-3">
                        <button
                            onClick={handleOpen}
                            disabled={securityState.softBlocked || !doc.source_link}
                            className={`flex flex-col items-center justify-center p-4 rounded-xl border transition-all gap-2 group ${securityState.softBlocked || !doc.source_link
                                ? 'bg-black/20 border-white/5 text-slate-600 cursor-not-allowed'
                                : 'bg-white/5 hover:bg-indigo-500/20 border-white/5 hover:border-indigo-500/50 text-slate-200'
                                }`}
                        >
                            <ExternalLink size={20} className={securityState.softBlocked ? "text-slate-600" : "text-slate-400 group-hover:text-indigo-400 transition-colors"} />
                            <span className="text-[10px] font-bold uppercase tracking-wide">Open</span>
                        </button>
                        <button
                            onClick={handleDownload}
                            disabled={securityState.softBlocked || !doc.source_link}
                            className={`flex flex-col items-center justify-center p-4 rounded-xl border transition-all gap-2 group ${securityState.softBlocked || !doc.source_link
                                ? 'bg-black/20 border-white/5 text-slate-600 cursor-not-allowed'
                                : 'bg-white/5 hover:bg-emerald-500/20 border-white/5 hover:border-emerald-500/50 text-slate-200'
                                }`}
                        >
                            <Download size={20} className={securityState.softBlocked ? "text-slate-600" : "text-slate-400 group-hover:text-emerald-400 transition-colors"} />
                            <span className="text-[10px] font-bold uppercase tracking-wide">Download</span>
                        </button>
                    </div>
                </CollapsibleSection>

            </div>
        </div>
    );
};

export default DocDetailDrawer;