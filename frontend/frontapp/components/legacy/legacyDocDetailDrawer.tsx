import React, { useState } from 'react';
import { extractVersionMeta, computeGroupKey } from '../services/dataService';
import { useOmniHub } from '../context/OmniHubContext';
import { X, ChevronDown, ChevronRight, Download, ExternalLink, FolderInput, Shield, ShieldAlert, ShieldCheck, Clock, HardDrive, User, Star, BrainCircuit, Check, Ban, Lock, GitBranch } from 'lucide-react';

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
  <div className="border border-white/5 rounded-lg bg-white/5 overflow-hidden mb-3 transition-all duration-200 hover:border-white/10">
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

const DocDetailDrawer: React.FC = () => {
  const { 
      selectedDoc: doc, setSelectedDoc, 
      addLog, securityState, updateDoc, reportSecurityEvent 
  } = useOmniHub();
  
  const [sections, setSections] = useState({
    summary: true,
    metadata: false,
    actions: true
  });
  const [rejectMode, setRejectMode] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  if (!doc) return null;

  const onClose = () => setSelectedDoc(null);

  // Compute Version Info
  const versionMeta = extractVersionMeta(doc.name);
  const groupKey = computeGroupKey(doc.name);
  const isVersioned = versionMeta.versionNumber !== undefined || versionMeta.versionStatus !== null;

  const toggleSection = (key: keyof typeof sections) => {
    setSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const getSecurityBadge = (level: string) => {
    switch(level) {
      case 'high': 
        return <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-red-500/10 border border-red-500/30 text-red-400 text-[10px] font-bold uppercase tracking-wider shadow-[0_0_10px_rgba(239,68,68,0.2)]"><ShieldAlert size={12}/> HIGH SEC</div>;
      case 'medium': 
        return <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-amber-500/10 border border-amber-500/30 text-amber-400 text-[10px] font-bold uppercase tracking-wider shadow-[0_0_10px_rgba(245,158,11,0.2)]"><Shield size={12}/> MEDIUM SEC</div>;
      default: 
        return <div className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-[10px] font-bold uppercase tracking-wider shadow-[0_0_10px_rgba(16,185,129,0.2)]"><ShieldCheck size={12}/> LOW SEC</div>;
    }
  };

  const handleOpen = () => {
    if (securityState.softBlocked) {
        reportSecurityEvent('BLOCK_ATTEMPT');
        addLog('보안 정책에 의해 문서 열람 차단됨', 'WARN', 'SECURITY');
        return;
    }
    
    if (doc.id.startsWith('ad-') || doc.driveUrl === '#' || doc.driveUrl === '') {
        addLog(`문서 열기(Demo) -> ${doc.name} (실제 링크 없음)`, 'INFO', 'SECURITY');
    } else {
        window.open(doc.driveUrl, '_blank');
        addLog(`문서 열기 -> ${doc.name}`, 'INFO');
    }
  };

  const handleDownload = () => {
    if (securityState.softBlocked) {
        reportSecurityEvent('BLOCK_ATTEMPT');
        addLog(`보안 정책에 의해 다운로드 차단됨`, 'WARN', 'SECURITY');
        return;
    }
    reportSecurityEvent('DOWNLOAD');
    addLog(`다운로드 실행됨 -> ${doc.name}`, 'INFO', 'SECURITY');
  };

  const handleApprove = () => {
      if (securityState.softBlocked) {
          reportSecurityEvent('BLOCK_ATTEMPT');
          addLog(`보안 정책에 의해 승인 차단됨`, 'WARN', 'SECURITY');
          return;
      }
      updateDoc(doc.id, { status: 'approved' });
  };

  const handleRejectSubmit = () => {
      if (!rejectReason.trim()) return;
      updateDoc(doc.id, { status: 'rejected' });
      setRejectMode(false);
  };

  return (
    <div className="absolute top-6 bottom-6 right-6 w-[420px] bg-[#050508]/80 backdrop-blur-2xl border border-white/10 shadow-[0_0_50px_rgba(0,0,0,0.6)] z-40 flex flex-col rounded-2xl overflow-hidden ring-1 ring-white/5 animate-in slide-in-from-right-8 duration-500 group">
      {/* Holographic Border Effect */}
      <div className="absolute inset-0 pointer-events-none rounded-2xl border border-white/5 box-border"></div>
      <div className="absolute top-0 right-0 w-32 h-32 bg-cyan-500/10 blur-3xl pointer-events-none rounded-full"></div>

      {/* Header */}
      <div className="shrink-0 flex flex-col px-6 py-5 border-b border-white/10 bg-gradient-to-r from-white/5 to-transparent relative">
        <button onClick={onClose} className="absolute top-4 right-4 p-2 hover:bg-white/10 rounded-full text-slate-400 hover:text-white transition-colors z-10">
          <X size={20} />
        </button>

        {isVersioned && (
            <div className="flex items-center gap-2 mb-2 text-[9px] font-mono text-violet-400">
                <GitBranch size={12} />
                <span className="opacity-70 tracking-widest">VERSION_GROUP:</span>
                <span className="font-bold text-violet-300 truncate max-w-[200px] bg-violet-500/10 px-1 rounded">{groupKey}</span>
            </div>
        )}

        <h2 className="text-xl font-bold text-white truncate pr-8 leading-tight mb-3 tracking-tight drop-shadow-md keep-all" title={doc.name}>{doc.name}</h2>
        
        <div className="flex flex-wrap items-center gap-2">
            {getSecurityBadge(doc.security)}
            {doc.ssotRating && (
                <div className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                    doc.ssotRating === 'gold' 
                    ? 'bg-amber-500/10 border-amber-500/30 text-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.2)]' 
                    : 'bg-slate-500/10 border-slate-500/30 text-slate-400'
                }`}>
                    <Star 
                        size={10} 
                        className={doc.ssotRating === 'gold' ? "fill-amber-400" : "fill-slate-400"} 
                    />
                    SSOT {doc.ssotRating}
                </div>
            )}
            {versionMeta.versionStatus && (
                <div className="px-2 py-0.5 rounded bg-violet-500/10 border border-violet-500/30 text-violet-300 text-[10px] font-bold uppercase">
                    {versionMeta.versionStatus}
                </div>
            )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6 scrollbar-thin">
        
        {/* PENDING: AI Suggestion Card */}
        {doc.status === 'pending' && (
            <div className="mb-6 bg-gradient-to-br from-indigo-950/50 to-slate-900 border border-indigo-500/30 rounded-xl p-5 shadow-lg relative overflow-hidden group">
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
                        <span className="text-indigo-300 truncate max-w-[180px]">{doc.folderPath}</span>
                    </div>
                     <div className="flex justify-between items-center border-b border-white/5 pb-2">
                        <span className="text-slate-500 font-bold">SEC_LEVEL</span>
                        <span className="font-bold text-amber-400 uppercase tracking-wider">{doc.security}</span>
                    </div>
                    <div>
                        <span className="text-slate-500 block mb-2 font-bold">TAGS</span>
                        <div className="flex flex-wrap gap-1.5">
                            {doc.tags.map(t => <span key={t} className="px-2 py-0.5 bg-white/5 rounded text-[10px] text-slate-300 border border-white/5">#{t}</span>)}
                        </div>
                    </div>
                </div>

                {!rejectMode ? (
                    <div className="grid grid-cols-2 gap-3 relative z-10">
                        <button 
                            onClick={handleApprove}
                            disabled={securityState.softBlocked}
                            className={`flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-bold transition-all ${
                                securityState.softBlocked 
                                ? 'bg-slate-800 text-slate-500 cursor-not-allowed border border-white/5'
                                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/20 active:scale-95'
                            }`}
                        >
                             {securityState.softBlocked ? <Lock size={14}/> : <Check size={16} />} 
                             APPROVE
                        </button>
                        <button 
                            onClick={() => setRejectMode(true)}
                            className="flex items-center justify-center gap-2 py-2.5 bg-white/5 hover:bg-red-500/20 text-slate-300 hover:text-red-200 border border-white/10 hover:border-red-500/30 rounded-lg text-xs font-bold transition-all active:scale-95"
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
                            className="w-full bg-[#050508] border border-red-500/30 rounded-lg p-3 text-xs text-slate-200 focus:border-red-500 focus:outline-none h-20 placeholder-slate-600 font-mono keep-all"
                        />
                        <div className="flex gap-2">
                            <button 
                                onClick={handleRejectSubmit}
                                className="flex-1 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-xs font-bold shadow-lg shadow-red-900/20"
                            >
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
                 {securityState.softBlocked && (
                    <div className="mt-3 text-[10px] text-center text-amber-500 flex items-center justify-center gap-1.5 font-bold">
                        <Lock size={10}/> LOCKED BY SECURITY POLICY
                    </div>
                )}
            </div>
        )}

        {/* 1. AI Summary */}
        <CollapsibleSection 
          title="AI Executive Summary" 
          isOpen={sections.summary} 
          onToggle={() => toggleSection('summary')}
        >
           <ul className="space-y-4">
              {doc.aiSummary3.map((line, idx) => (
                <li key={idx} className="flex gap-4 text-sm text-slate-300 leading-relaxed group">
                   <div className="shrink-0 w-1.5 h-1.5 rounded-full bg-cyan-500 mt-2 group-hover:shadow-[0_0_8px_#22d3ee] transition-all"></div>
                   <span className="opacity-90 keep-all font-light">{line}</span>
                </li>
              ))}
           </ul>
        </CollapsibleSection>

        {/* 2. Metadata */}
        <CollapsibleSection 
          title="File Metadata" 
          isOpen={sections.metadata} 
          onToggle={() => toggleSection('metadata')}
        >
           <div className="grid grid-cols-2 gap-y-5 gap-x-4 text-xs">
              <div className="space-y-1.5">
                  <div className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-wider text-[10px]"><HardDrive size={12}/> Size</div>
                  <div className="text-slate-200 font-mono text-sm tracking-wide">{Math.round(doc.sizeKB)} KB</div>
              </div>
              <div className="space-y-1.5">
                  <div className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-wider text-[10px]"><Clock size={12}/> Updated</div>
                  <div className="text-slate-200 font-mono text-sm tracking-wide">{new Date(doc.updatedAt).toLocaleDateString()}</div>
              </div>
              <div className="col-span-2 space-y-1.5">
                  <div className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-wider text-[10px]"><User size={12}/> Owner</div>
                  <div className="text-slate-200 font-mono text-xs flex items-center gap-2 p-2 bg-black/20 rounded border border-white/5">
                      <div className="w-5 h-5 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-600 text-[9px] flex items-center justify-center text-white font-bold shadow-md">
                          {doc.owner.substring(0,2).toUpperCase()}
                      </div>
                      {doc.owner}
                  </div>
              </div>
              <div className="col-span-2 space-y-1.5">
                  <div className="text-slate-500 flex items-center gap-1.5 font-bold uppercase tracking-wider text-[10px]"><FolderInput size={12}/> Path</div>
                  <div className="text-slate-400 font-mono text-[10px] break-all bg-black/20 p-2.5 rounded border border-white/5">
                    {doc.folderPath}
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
                    disabled={securityState.softBlocked}
                    className={`flex flex-col items-center justify-center p-4 rounded-lg border transition-all gap-2 group ${
                        securityState.softBlocked
                        ? 'bg-black/20 border-white/5 text-slate-600 cursor-not-allowed'
                        : 'bg-white/5 hover:bg-cyan-500/10 border-white/5 hover:border-cyan-500/30 text-slate-300 hover:text-cyan-300'
                    }`}
                >
                    <ExternalLink size={20} className={securityState.softBlocked ? "text-slate-600" : "text-slate-400 group-hover:text-cyan-400 transition-colors"} />
                    <span className="text-[10px] font-bold uppercase tracking-wide">Open</span>
                </button>
                <button 
                    onClick={handleDownload}
                    disabled={securityState.softBlocked}
                    className={`flex flex-col items-center justify-center p-4 rounded-lg border transition-all gap-2 group ${
                        securityState.softBlocked
                        ? 'bg-black/20 border-white/5 text-slate-600 cursor-not-allowed'
                        : 'bg-white/5 hover:bg-emerald-500/10 border-white/5 hover:border-emerald-500/30 text-slate-300 hover:text-emerald-300'
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