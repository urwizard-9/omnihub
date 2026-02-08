import React, { useState, useEffect } from 'react';
import { AIService } from '../../services/aiService';
import { TreeResponse, FolderNode, FileNode } from '../../types';
import { Folder, FileText, ChevronRight, ChevronDown, FolderOpen } from 'lucide-react';

/**
 * [DocTreeBrowser]
 * 폴더 트리 기반의 문서 탐색기 컴포넌트입니다.
 * - 윈도우 탐색기처럼 폴더 > 하위폴더 > 파일 구조를 계층적으로 표시합니다.
 * - 폴더 클릭 시 하위 내용을 동적으로 로딩합니다 (Lazy Loading).
 * - 파일 클릭 시 부모 컴포넌트에게 문서 ID를 전달합니다.
 */

// ========== Props 인터페이스 ==========
interface Props {
    onFileClick: (docId: string) => void; // 파일 클릭 시 호출되는 콜백 (부모에게 이벤트 위임)
}

// ========== 트리 노드 컴포넌트 (재귀적 렌더링) ==========
interface TreeNodeProps {
    path: string;           // 폴더 경로 (API 호출용)
    name: string;           // 표시할 이름
    type: 'folder' | 'file'; // 노드 타입
    docId?: string;         // 파일인 경우 문서 ID
    level: number;          // 들여쓰기 깊이
    onFileClick: (id: string) => void;
}

const TreeNode: React.FC<TreeNodeProps> = ({ path, name, type, docId, level, onFileClick }) => {
    // ========== 상태 관리 ==========
    const [expanded, setExpanded] = useState(false);        // 폴더 열림/닫힘 상태
    const [data, setData] = useState<TreeResponse | null>(null); // 하위 폴더/파일 데이터
    const [loading, setLoading] = useState(false);          // 로딩 상태

    // ========== 클릭 핸들러 (폴더 확장 또는 파일 선택) ==========
    const handleExpand = async (e: React.MouseEvent) => {
        e.stopPropagation(); // 이벤트 버블링 방지

        // 1. 파일인 경우 -> 부모에게 알림
        if (type === 'file') {
            if (docId) onFileClick(docId);
            return;
        }

        // 2. 폴더인 경우 -> 토글 (열기/닫기)
        if (expanded) {
            setExpanded(false); // 이미 열려있으면 닫기
        } else {
            setExpanded(true);
            // 데이터가 없으면 API 호출 (최초 1회만, 캐싱됨)
            if (!data) {
                setLoading(true);
                try {
                    const res = await AIService.getTreeStructure(path);
                    console.log("Tree Data for path:", path, res); // [Debug]
                    setData(res);
                } catch (err) {
                    console.error("Tree Load Error:", err);
                } finally {
                    setLoading(false);
                }
            }
        }
    };

    // ========== [UI/UX] 트리 노드 렌더링 ==========
    return (
        <div className="select-none">
            {/* [UI/UX] 노드 행 (폴더/파일 한 줄) */}
            <div
                className={`flex items-center gap-2 py-1.5 px-2 hover:bg-white/5 rounded-lg cursor-pointer transition-colors ${expanded ? 'text-white' : 'text-slate-400 hover:text-slate-200'}`}
                style={{ paddingLeft: `${level * 12 + 8}px` }} // 깊이에 따른 들여쓰기
                onClick={handleExpand}
            >
                {/* [UI/UX] 폴더 확장 화살표 아이콘 */}
                {type === 'folder' && (
                    <span className="text-slate-600">
                        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </span>
                )}

                {/* [UI/UX] 폴더/파일 아이콘 */}
                {type === 'folder' ? (
                    expanded ? <FolderOpen size={16} className="text-indigo-400" /> : <Folder size={16} className="text-indigo-500/80" />
                ) : (
                    <FileText size={16} className="text-emerald-500/80" />
                )}

                {/* [UI/UX] 이름 텍스트 */}
                <span className="text-sm truncate">{name}</span>
            </div>

            {/* [UI/UX] 하위 노드 (재귀적 렌더링) */}
            {expanded && data && (
                <div className="animate-in slide-in-from-top-1 duration-200">
                    {/* 하위 폴더들 */}
                    {data.folders?.map(f => (
                        <TreeNode
                            key={f.path}
                            path={f.path}
                            name={f.name}
                            type="folder"
                            level={level + 1}
                            onFileClick={onFileClick}
                        />
                    ))}

                    {/* 하위 파일들 */}
                    {data.files?.map(f => {
                        console.log("File Node:", f); // [Debug]
                        return (
                            <TreeNode
                                key={f.doc_id}
                                path=""
                                name={f.name || (f as any).title || "Untitled"}
                                type="file"
                                docId={f.doc_id}
                                level={level + 1}
                                onFileClick={onFileClick}
                            />
                        );
                    })}

                    {/* [UI/UX] 빈 폴더 표시 */}
                    {data.folders.length === 0 && data.files.length === 0 && (
                        <div className="py-1 px-4 text-xs text-slate-600 italic" style={{ paddingLeft: `${(level + 1) * 12 + 20}px` }}>
                            (Empty)
                        </div>
                    )}
                </div>
            )}

            {/* [UI/UX] 로딩 표시 */}
            {expanded && loading && (
                <div className="py-1 px-4 text-xs text-slate-600 animate-pulse" style={{ paddingLeft: `${(level + 1) * 12 + 20}px` }}>
                    Loading...
                </div>
            )}
        </div>
    );
};

// ========== 메인 컴포넌트 (루트 노드 렌더링) ==========
const DocTreeBrowser: React.FC<Props> = ({ onFileClick }) => {
    return (
        // ========== [UI/UX] 전체 컨테이너 ==========
        <div className="h-full bg-[#09090b] border-r border-white/5 flex flex-col">
            {/* [UI/UX] 헤더 */}
            <div className="p-4 border-b border-white/5 font-bold text-slate-300 text-sm flex items-center gap-2">
                <FolderOpen size={18} className="text-indigo-500" />
                문서 탐색기
            </div>

            {/* [UI/UX] 스크롤 영역 (트리 본문) */}
            <div className="flex-1 overflow-y-auto p-2 scrollbar-thin scrollbar-thumb-white/10">
                {/* 루트 노드 (최상위 폴더) */}
                <TreeNode
                    path="/"
                    name="Root"
                    type="folder"
                    onFileClick={onFileClick}
                    level={0}
                />
            </div>
        </div>
    );
};

export default DocTreeBrowser;
