import React, { useState, useEffect, useCallback } from 'react';
import { useOmniHub } from '../../context/OmniHubContext';
import { DocRecord } from '../../types';
import { FileText, ChevronRight, ChevronDown, Database, Filter, FolderTree } from 'lucide-react';

// ========== Types for Recursive Tree Data ==========
interface TreeNode {
    name: string;
    path: string; // "folder_path" in API
    children_folders: TreeNode[];
    children_docs: TreeDoc[];
    doc_count?: number; // Optional
}

interface TreeDoc {
    doc_id: string;
    title: string;
    mime_type?: string;
    doc_metadata?: any;
}


// ========== Component: Tree File Item (Leaf) ==========
interface TreeDocItemProps {
    doc: TreeDoc;
    isSelected: boolean;
    onClick: (docId: string) => void;
}

const TreeDocItem: React.FC<TreeDocItemProps> = ({ doc, isSelected, onClick }) => (
    <div
        id={`tree-doc-${doc.doc_id}`}
        onClick={(e) => { e.stopPropagation(); onClick(doc.doc_id); }}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-md cursor-pointer text-xs transition-all group/doc border border-transparent ${isSelected
            ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30 shadow-[0_0_10px_rgba(99,102,241,0.2)] font-bold translate-x-1'
            : 'text-slate-400 hover:text-indigo-200 hover:bg-white/5'
            }`}
    >
        <FileText size={12} className={`shrink-0 ${isSelected ? 'text-indigo-400' : 'opacity-40 group-hover/doc:opacity-100'}`} />
        <span className="truncate tracking-tight">{doc.title}</span>
    </div>
);


const INITIAL_FOLDER_LIMIT = 8;
const LOAD_MORE_STEP = 20;

// ========== Component: Tree Folder Item (Recursive) ==========
interface TreeFolderItemProps {
    node: ApiNode;
    level: number;
    expandedFolders: Set<string>;
    onToggle: (path: string) => void;
    selectedDocId?: string | null;
    onFileClick: (docId: string) => void;
    filterText: string;
    folderLimits: Record<string, number>;
    onLoadMore: (path: string) => void;
}

const TreeFolderItem: React.FC<TreeFolderItemProps> = ({
    node,
    level,
    expandedFolders,
    onToggle,
    selectedDocId,
    onFileClick,
    filterText,
    folderLimits,
    onLoadMore
}) => {
    const isExpanded = expandedFolders.has(node.id) || (filterText.length > 0 && node.name.toLowerCase().includes(filterText.toLowerCase()));

    // Split children into folders and files
    const folders = node.children?.filter(c => c.is_folder) || [];
    const files = node.children?.filter(c => !c.is_folder) || [];

    // Pagination Logic
    const limit = folderLimits[node.id] || INITIAL_FOLDER_LIMIT;
    const isFiltered = filterText.length > 0;
    const visibleFiles = isFiltered ? files : files.slice(0, limit);
    const remainingFiles = isFiltered ? 0 : files.length - limit;

    return (
        <div className="animate-in fade-in slide-in-from-left-1 duration-200">
            <div
                onClick={(e) => { e.stopPropagation(); onToggle(node.id); }}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-all border border-transparent group ${isExpanded
                        ? 'bg-amber-500/10 border-amber-500/20 text-amber-200'
                        : 'hover:bg-white/5 text-slate-400'
                    }`}
            >
                <div className="p-0.5 text-slate-500 hover:text-white transition-colors">
                    {node.children && node.children.length > 0 ? (
                        isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
                    ) : <div className="w-3.5" />}
                </div>

                <Database size={14} className={isExpanded ? "text-amber-400 drop-shadow-[0_0_5px_rgba(251,191,36,0.5)]" : "text-slate-600 group-hover:text-amber-500/50"} />

                <span className="text-xs font-bold truncate flex-1 tracking-tight">{node.name}</span>
                <span className="text-[9px] bg-white/5 px-1.5 py-0.5 rounded border border-white/5 text-slate-500 font-mono">
                    {node.children?.length || 0}
                </span>
            </div>

            {isExpanded && node.children && (
                <div className="border-l border-white/10 ml-4 mb-1 space-y-0.5 pl-2">
                    {/* Folders first */}
                    {folders.map(child => (
                        <RecursiveItem
                            key={child.id}
                            node={child}
                            level={level + 1}
                            expandedFolders={expandedFolders}
                            onToggle={onToggle}
                            selectedDocId={selectedDocId}
                            onFileClick={onFileClick}
                            filterText={filterText}
                            folderLimits={folderLimits}
                            onLoadMore={onLoadMore}
                        />
                    ))}

                    {/* Files next */}
                    {visibleFiles.map(child => (
                        <RecursiveItem
                            key={child.id}
                            node={child}
                            level={level + 1}
                            expandedFolders={expandedFolders}
                            onToggle={onToggle}
                            selectedDocId={selectedDocId}
                            onFileClick={onFileClick}
                            filterText={filterText}
                            folderLimits={folderLimits}
                            onLoadMore={onLoadMore}
                        />
                    ))}

                    {/* Load More Button */}
                    {!isFiltered && remainingFiles > 0 && (
                        <button
                            onClick={(e) => { e.stopPropagation(); onLoadMore(node.id); }}
                            className="w-full text-left px-3 py-1.5 text-[10px] text-amber-500/70 hover:text-amber-400 hover:bg-white/5 rounded transition-colors italic font-medium flex items-center gap-1"
                        >
                            <span>+ {remainingFiles} more files...</span>
                        </button>
                    )}

                    {node.children.length === 0 && (
                        <div className="px-3 py-1.5 text-[10px] text-slate-600 italic">Empty</div>
                    )}
                </div>
            )}
        </div>
    );
};


// ========== Main Component: DocTreeBrowser ==========
interface Props {
    onFileClick: (docId: string) => void;
}

const DocTreeBrowser: React.FC<Props> = ({ onFileClick }) => {
    const {
        treeData,
        expandedFolders, setExpandedFolders,
        treeSearchQuery, setTreeSearchQuery,
        docs, selectedDoc, scrollToTreeItem,
        folderLimits, setFolderLimits
    } = useOmniHub();

    // Toggle Handler
    const handleToggle = useCallback((path: string) => {
        setExpandedFolders(prev => {
            const next = new Set(prev);
            if (next.has(path)) next.delete(path);
            else next.add(path);
            return next;
        });
        // Ensure limit is initialized
        setFolderLimits(prev => {
            if (!prev[path]) return { ...prev, [path]: INITIAL_FOLDER_LIMIT };
            return prev;
        });
    }, [setExpandedFolders, setFolderLimits]);

    // Load More Handler
    const handleLoadMore = useCallback((path: string) => {
        setFolderLimits(prev => ({
            ...prev,
            [path]: (prev[path] || INITIAL_FOLDER_LIMIT) + LOAD_MORE_STEP
        }));
    }, [setFolderLimits]);

    // Handle File Click (Integrate with Context)
    const handleFileClick = useCallback((docId: string) => {
        onFileClick(docId);
    }, [onFileClick]);

    // Scroll to Selection (Effect)
    useEffect(() => {
        if (selectedDoc && selectedDoc.actualPath) {
            // TODO: Enhance scrollToTreeItem to handle Recursive Structure
        }
    }, [selectedDoc]);

    if (!treeData) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-slate-600 space-y-2">
                <Database size={24} className="animate-pulse opacity-50" />
                <span className="text-xs italic">Loading File System...</span>
            </div>
        );
    }

    return (
        <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#09090b] border-r border-white/5">
            {/* Header / Search */}
            <div className="px-6 pt-6 pb-2 shrink-0">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2 text-amber-400">
                        <FolderTree size={16} />
                        <h2 className="font-bold uppercase tracking-wider text-xs">
                            File System
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

            {/* Tree Content */}
            <div className="flex-1 overflow-y-auto px-4 pb-6 scrollbar-thin">
                <RecursiveTreeRoot
                    node={treeData}
                    expandedFolders={expandedFolders}
                    onToggle={handleToggle}
                    selectedDocId={selectedDoc?.id}
                    onFileClick={handleFileClick}
                    filterText={treeSearchQuery}
                    folderLimits={folderLimits}
                    onLoadMore={handleLoadMore}
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
    );
};

// ========== Adapter & Recursive Component ==========

interface ApiNode {
    name: string;
    id: string; // path
    is_folder: boolean;
    children?: ApiNode[];
    mime_type?: string;
}

const RecursiveTreeRoot: React.FC<{
    node: ApiNode,
    expandedFolders: Set<string>,
    onToggle: (path: string) => void,
    selectedDocId?: string | null,
    onFileClick: (id: string) => void,
    filterText: string,
    folderLimits: Record<string, number>,
    onLoadMore: (path: string) => void
}> = ({ node, expandedFolders, onToggle, selectedDocId, onFileClick, filterText, folderLimits, onLoadMore }) => {

    if (node.id === '/') {
        return (
            <div className="space-y-0.5">
                {node.children?.map(child => (
                    <RecursiveItem
                        key={child.id}
                        node={child}
                        level={0}
                        expandedFolders={expandedFolders}
                        onToggle={onToggle}
                        selectedDocId={selectedDocId}
                        onFileClick={onFileClick}
                        filterText={filterText}
                        folderLimits={folderLimits}
                        onLoadMore={onLoadMore}
                    />
                ))}
            </div>
        )
    }

    return <RecursiveItem node={node} level={0} expandedFolders={expandedFolders} onToggle={onToggle} selectedDocId={selectedDocId} onFileClick={onFileClick} filterText={filterText} folderLimits={folderLimits} onLoadMore={onLoadMore} />;
};

const RecursiveItem: React.FC<{
    node: ApiNode,
    level: number,
    expandedFolders: Set<string>,
    onToggle: (path: string) => void,
    selectedDocId?: string | null,
    onFileClick: (id: string) => void,
    filterText: string,
    folderLimits: Record<string, number>,
    onLoadMore: (path: string) => void
}> = (props) => {
    const { node, selectedDocId, onFileClick, filterText } = props;

    if (!node.is_folder) {
        // Check filtering
        if (filterText && !node.name.toLowerCase().includes(filterText.toLowerCase())) return null;

        const doc: TreeDoc = { doc_id: node.id, title: node.name, mime_type: node.mime_type };
        return <TreeDocItem doc={doc} isSelected={selectedDocId === node.id} onClick={onFileClick} />;
    }

    // Delegate to TreeFolderItem which handles recursion via RecursiveItem
    return <TreeFolderItem {...props} />;
};
export default DocTreeBrowser;
