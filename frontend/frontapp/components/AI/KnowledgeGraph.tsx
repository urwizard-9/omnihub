import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import * as d3 from 'd3';
import { AIService } from '../../services/aiService';
import { DocRecord } from '../../types';
import { Network, Zap, RefreshCw, Minus, Plus, Target, Crosshair, FolderOpen } from 'lucide-react';
import { useOmniHub } from '../../context/OmniHubContext';

// ========== 타입 정의 ==========
interface KnowledgeGraphProps {
    onDocClick?: (docId: string) => void;
}

interface SimulationNode extends d3.SimulationNodeDatum {
    id: string;
    label?: string;
    group?: 'document' | 'concept' | 'virtualPath';
    type?: string;
    mentions?: number;
    size?: number;
    degree?: number;
    // 추가 속성
    data?: any; // 원본 DocRecord 등
}

interface SimulationLink extends d3.SimulationLinkDatum<SimulationNode> {
    source: string | SimulationNode;
    target: string | SimulationNode;
    type?: string; // 'version', 'related', etc.
    rank_score?: number;
}

// ========== 사이버펑크 컬러 팔레트 ==========
const CYBER_COLORS = {
    background: '#0b0f19',
    backgroundGradient: 'linear-gradient(135deg, #0b0f19 0%, #0f172a 50%, #1a1a2e 100%)',
    gridDot: 'rgba(34, 211, 238, 0.06)',
    neon: {
        cyan: '#22d3ee',
        violet: '#a78bfa',
        amber: '#fbbf24',
        emerald: '#34d399',
        rose: '#fb7185',
        sky: '#38bdf8',
        fuchsia: '#e879f9',
        group: '#c084fc', // 그룹 노드 색상
        versionLink: '#c084fc',
    },
    linkDefault: '#475569',
    linkHighlight: '#22d3ee',
    text: '#e2e8f0',
    textMuted: '#94a3b8',
    nodeStroke: 'rgba(255, 255, 255, 0.2)',
};

const getNodeNeonColor = (d: SimulationNode): string => {
    if (d.group === 'document') {
        if (d.data?.status === 'pending') return CYBER_COLORS.neon.amber;
        return CYBER_COLORS.neon.emerald;
    }
    switch (d.type?.toUpperCase()) {
        case 'PERSON': return CYBER_COLORS.neon.violet;
        case 'ORGANIZATION':
        case 'ORG': return CYBER_COLORS.neon.amber;
        case 'GPE':
        case 'LOCATION': return CYBER_COLORS.neon.sky;
        case 'EVENT': return CYBER_COLORS.neon.rose;
        case 'METRIC': return CYBER_COLORS.neon.fuchsia;
        default: return CYBER_COLORS.neon.cyan;
    }
};

const getNodeRadius = (d: SimulationNode): number => {
    const baseDegree = d.degree || 1;
    if (d.group === 'document') {
        return Math.min(5 + Math.sqrt(baseDegree) * 2, 14);
    }
    return Math.min(8 + Math.sqrt(baseDegree) * 3, 32);
};

const getFontSize = (d: SimulationNode): number => {
    const degree = d.degree || 1;
    if (d.group === 'document') return 9;
    return Math.min(9 + Math.sqrt(degree) * 1.5, 14);
};

const truncateLabel = (text: string, maxLength: number = 18): string => {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.slice(0, maxLength - 1) + '…';
};

const KnowledgeGraph: React.FC<KnowledgeGraphProps> = ({ onDocClick }) => {
    const { aiStatus } = useOmniHub();
    const svgRef = useRef<SVGSVGElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

    // Raw Data (Server Response)
    const [rawNodes, setRawNodes] = useState<SimulationNode[]>([]);
    const [rawLinks, setRawLinks] = useState<SimulationLink[]>([]);

    // UI State
    const [loading, setLoading] = useState(false);
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

    // New Features State
    const [viewMode, setViewMode] = useState<'default' | 'local'>('default');
    const [showRestricted, setShowRestricted] = useState(false);
    const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

    const [stats, setStats] = useState({ nodes: 0, links: 0 });

    // ========== 데이터 로드 ==========
    const loadInit = useCallback(async (silent = false) => {
        if (!silent) setLoading(true);
        try {
            // Updated: Call with mode="overview"
            const data = await AIService.getGraphInit({
                mode: 'overview',
                max_concepts: 50,
                max_edges: 160,
                include_docs: false
            });
            if (data && data.nodes) {
                // Initialize raw nodes with degree info
                const simNodes = data.nodes.map(n => ({ ...n, data: n })) as SimulationNode[];
                const rawEdges = data.links || (data as any).edges || [];
                const simLinks = rawEdges.map((l: any) => ({ ...l })) as SimulationLink[];

                // Initial Degree Calc
                const degreeMap: Record<string, number> = {};
                simLinks.forEach(link => {
                    const srcId = typeof link.source === 'string' ? link.source : (link.source as any).id;
                    const tgtId = typeof link.target === 'string' ? link.target : (link.target as any).id;
                    degreeMap[srcId] = (degreeMap[srcId] || 0) + 1;
                    degreeMap[tgtId] = (degreeMap[tgtId] || 0) + 1;
                });
                simNodes.forEach(node => { node.degree = degreeMap[node.id] || 1; });

                setRawNodes(simNodes);
                setRawLinks(simLinks);
            }
        } catch (e) {
            console.error("Graph Load Error:", e);
        } finally {
            if (!silent) setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadInit();
    }, [loadInit]);

    // Resize Observer
    useEffect(() => {
        if (!containerRef.current) return;
        const observer = new ResizeObserver((entries) => {
            if (!entries.length) return;
            const { width, height } = entries[0].contentRect;
            setDimensions({ width, height });
        });
        observer.observe(containerRef.current);
        return () => observer.disconnect();
    }, []);

    // ========== 데이터 필터링 및 가공 ==========
    const { nodes: groupedNodes, links: groupedLinks } = useMemo(() => {
        let filteredNodes = rawNodes;
        let filteredLinks = rawLinks;

        // 1. Security Filtering (Client-side)
        if (!showRestricted) {
            const restrictedIds = new Set<string>();
            filteredNodes = filteredNodes.filter(n => {
                if (n.group === 'document') {
                    const data = n.data as DocRecord; // Safety: data is injected in loadInit
                    if (data?.security === 'high') {
                        restrictedIds.add(n.id);
                        return false;
                    }
                }
                return true;
            });
            filteredLinks = filteredLinks.filter(l => {
                const srcId = typeof l.source === 'string' ? l.source : (l.source as any).id;
                const tgtId = typeof l.target === 'string' ? l.target : (l.target as any).id;
                return !restrictedIds.has(srcId) && !restrictedIds.has(tgtId);
            });
        }

        // 2. View Mode Filtering (Local View)
        if (viewMode === 'local' && selectedNodeId) {
            // Find neighbors of selected node + selected node itself
            const neighborIds = new Set<string>();
            neighborIds.add(selectedNodeId);

            // 1-hop neighbors
            filteredLinks.forEach(l => {
                const srcId = typeof l.source === 'string' ? l.source : (l.source as any).id;
                const tgtId = typeof l.target === 'string' ? l.target : (l.target as any).id;
                if (srcId === selectedNodeId) neighborIds.add(tgtId);
                if (tgtId === selectedNodeId) neighborIds.add(srcId);
            });

            filteredNodes = filteredNodes.filter(n => neighborIds.has(n.id));
            filteredLinks = filteredLinks.filter(l => {
                const srcId = typeof l.source === 'string' ? l.source : (l.source as any).id;
                const tgtId = typeof l.target === 'string' ? l.target : (l.target as any).id;
                return neighborIds.has(srcId) && neighborIds.has(tgtId);
            });
        }

        // 3. Virtual Paths (Folders)
        // Grouping logic removed, but keeping virtual folders if doc has folderPath
        const folderPaths = new Set<string>();
        const finalNodes: SimulationNode[] = [...filteredNodes];
        const linkDedup = new Set<string>();
        const finalLinks: SimulationLink[] = [...filteredLinks];

        // Collect folders from visible docs
        filteredNodes.forEach(n => {
            if (n.group === 'document') {
                const path = n.data?.folderPath;
                if (path) folderPaths.add(path);
            }
        });

        // Create Folder Nodes
        const folderNodes: SimulationNode[] = [];
        folderPaths.forEach(path => {
            const folderId = `folder:${path}`;
            // Avoid duplicate pushing if folder node logic existed in rawNodes (it doesn't typically)
            folderNodes.push({
                id: folderId,
                label: path.split('/').pop() || path,
                group: 'virtualPath',
                data: { fullPath: path },
                degree: 0
            });
        });
        finalNodes.push(...folderNodes);

        // Link Docs to Folders
        filteredNodes.forEach(n => {
            if (n.group === 'document') {
                const fPath = n.data?.folderPath;
                if (fPath) {
                    const folderId = `folder:${fPath}`;
                    const key = `${folderId}-${n.id}`;
                    if (!linkDedup.has(key)) {
                        linkDedup.add(key);
                        finalLinks.push({
                            source: folderId, target: n.id,
                            type: 'folder_contain',
                            rank_score: 1.0 // Strong link
                        });
                    }
                }
            }
        });

        // Initialize linkDedup with existing links to filter duplicates if any
        filteredLinks.forEach(l => {
            const s = typeof l.source === 'string' ? l.source : (l.source as any).id;
            const t = typeof l.target === 'string' ? l.target : (l.target as any).id;
            linkDedup.add(`${s}-${t}`);
        });

        return { nodes: finalNodes, links: finalLinks };
    }, [rawNodes, rawLinks, showRestricted, viewMode, selectedNodeId]);

    // Stats Effect
    useEffect(() => {
        setStats({ nodes: groupedNodes.length, links: groupedLinks.length });
    }, [groupedNodes.length, groupedLinks.length]);

    // ========== D3 렌더링 ==========
    useEffect(() => {
        if (!svgRef.current || dimensions.width === 0 || groupedNodes.length === 0) return;
        const { width, height } = dimensions;
        const svg = d3.select(svgRef.current);
        svg.selectAll("*").remove();

        // --- Definitions (Glow Filters) ---
        const defs = svg.append("defs");
        Object.entries(CYBER_COLORS.neon).forEach(([key, color]) => {
            const filter = defs.append("filter").attr("id", `glow-${key}`).attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
            filter.append("feGaussianBlur").attr("stdDeviation", "2.5").attr("result", "coloredBlur");
            const feMerge = filter.append("feMerge");
            feMerge.append("feMergeNode").attr("in", "coloredBlur");
            feMerge.append("feMergeNode").attr("in", "SourceGraphic");
        });

        const g = svg.append("g");

        // Zoom
        const zoom = d3.zoom<SVGSVGElement, unknown>()
            .scaleExtent([0.1, 4])
            .on("zoom", (e) => {
                g.attr("transform", e.transform);
                // Reveal Doc Labels on Zoom > 1.2
                const k = e.transform.k;
                svg.selectAll(".doc-label").style("opacity", (d: any) => {
                    // Logic: If zoomed in OR node is hovered (handled separately), show label
                    return k > 1.2 ? 1 : 0;
                });
            });
        svg.call(zoom);
        zoomRef.current = zoom;
        // Initial center
        svg.call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2).scale(0.8));

        // Simulation
        const effectiveMode = viewMode === 'local' ? 'local' : 'default';

        const simulation = d3.forceSimulation<SimulationNode>(groupedNodes)
            .force("link", d3.forceLink<SimulationNode, SimulationLink>(groupedLinks)
                .id(d => d.id)
                .distance(d => {
                    if (d.type === 'version') return 40;
                    return effectiveMode === 'default' ? 120 : 90;
                })
                .strength(d => d.type === 'version' ? 1 : 0.3)) // Strength kept from legacy
            .force("charge", d3.forceManyBody().strength(d => {
                return effectiveMode === 'default' ? -400 : -300;
            }))
            .force("collide", d3.forceCollide().radius(d => {
                const node = d as SimulationNode;
                if (node.group === 'concept') return 50;
                if (node.group === 'virtualPath') return 60;
                return 35; // Default doc
            }).strength(0.7))
            .force("x", d3.forceX(0).strength(0.04))
            .force("y", d3.forceY(0).strength(0.04))
            .force("center", d3.forceCenter(0, 0));

        // Links
        const link = g.append("g").selectAll("line")
            .data(groupedLinks).join("line");

        // Link Styling
        link.attr("stroke", d => {
            if (d.type === 'folder_contain') return '#fbbf24';
            if (d.type === 'version') return CYBER_COLORS.neon.versionLink;
            return CYBER_COLORS.linkDefault;
        })
            .attr("stroke-width", d => {
                if (d.type === 'folder_contain') return 2;
                if (d.type === 'version') return 1.5;
                return (0.5 + (d.rank_score || 0) * 2);
            })
            .attr("stroke-opacity", d => {
                if (d.type === 'folder_contain') return 0.5;
                if (d.type === 'version') return 0.6;
                return 0.3;
            })
            .attr("stroke-dasharray", d => {
                if (d.type === 'version') return "none"; // Changed from "3,3" to "none" as per original intent for version links
                if (d.type === 'cooc' || d.type === 'related') return "3,3";
                if ((d.rank_score || 0) < 0.4) return "2,2";
                return "none";
            });

        // Nodes
        const node = g.append("g").selectAll("g")
            .data(groupedNodes).join("g")
            .attr("cursor", "pointer")
            .call(d3.drag<SVGGElement, SimulationNode>()
                .on("start", (event, d) => {
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    d.fx = d.x; d.fy = d.y;
                })
                .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
                .on("end", (event, d) => {
                    if (!event.active) simulation.alphaTarget(0);
                    d.fx = null; d.fy = null;
                }) as any
            );

        // Node Visuals
        node.each(function (d) {
            const el = d3.select(this);
            const r = getNodeRadius(d);
            const color = getNodeNeonColor(d);

            // Glow BG
            el.append("circle").attr("r", r + 5).attr("fill", color).attr("opacity", 0.15).attr("filter", `url(#glow-cyan)`);

            // Core
            el.append("circle").attr("r", r).attr("fill", `color-mix(in srgb, ${color} 20%, ${CYBER_COLORS.background})`)
                .attr("stroke", color).attr("stroke-width", 1.5);

            // Icon / Text
            if (d.group === 'virtualPath') {
                el.append("text").text("📂").attr("dy", 5).attr("text-anchor", "middle").attr("font-size", "14px");
            }

            // SSOT Star
            const hasSSOT = (d.group === 'document' && (d.data?.ssot_level === 'Gold' || d.data?.ssotRating));
            if (hasSSOT) {
                el.append("text").text("★").attr("x", 8).attr("y", -8).attr("fill", "#fbbf24").attr("font-size", "12px");
            }
        });

        // Labels (Conditional Visibility)
        const label = g.append("g").selectAll("text")
            .data(groupedNodes).join("text")
            .text(d => truncateLabel(d.label || d.id, 24))
            .attr("x", d => getNodeRadius(d) + 6)
            .attr("dy", 4)
            .attr("fill", CYBER_COLORS.text)
            .attr("font-size", d => getFontSize(d) + "px")
            .style("pointer-events", "none")
            .attr("text-shadow", "0 2px 4px rgba(0,0,0,0.8)")
            .style("opacity", d => {
                if (d.group === 'concept') return 1;
                return 0;
            })
            .attr("class", d => d.group === 'document' ? "doc-label" : "concept-label");

        // Neighbor Map for Highlighting
        const neighborMap: Map<string, Set<string>> = new Map();
        groupedLinks.forEach(link => {
            const srcId = typeof link.source === 'string' ? link.source : (link.source as SimulationNode).id;
            const tgtId = typeof link.target === 'string' ? link.target : (link.target as SimulationNode).id;
            if (!neighborMap.has(srcId)) neighborMap.set(srcId, new Set());
            if (!neighborMap.has(tgtId)) neighborMap.set(tgtId, new Set());
            neighborMap.get(srcId)!.add(tgtId);
            neighborMap.get(tgtId)!.add(srcId);
        });

        // Hover Effect
        node.on("mouseenter", (event, d) => {
            const neighbors = neighborMap.get(d.id) || new Set();
            node.transition().duration(200).style("opacity", n => (n.id === d.id || neighbors.has(n.id)) ? 1 : 0.1);
            link.transition().duration(200)
                .attr("stroke", l => {
                    const srcId = (l.source as SimulationNode).id;
                    const tgtId = (l.target as SimulationNode).id;
                    if (srcId === d.id || tgtId === d.id) return CYBER_COLORS.linkHighlight;
                    return l.type === 'version' ? CYBER_COLORS.neon.versionLink : CYBER_COLORS.linkDefault;
                })
                .attr("stroke-opacity", l => {
                    const srcId = (l.source as SimulationNode).id;
                    const tgtId = (l.target as SimulationNode).id;
                    return (srcId === d.id || tgtId === d.id) ? 1 : 0.05;
                })
                .attr("stroke-width", l => {
                    const srcId = (l.source as SimulationNode).id;
                    const tgtId = (l.target as SimulationNode).id;
                    return (srcId === d.id || tgtId === d.id) ? 2 : (l.type === 'version' ? 1.5 : 0.5);
                });
            label.transition().duration(200).style("opacity", l => (l.id === d.id || neighbors.has(l.id)) ? 1 : 0.1);
        })
            .on("mouseleave", () => {
                node.transition().duration(300).style("opacity", 1);
                link.transition().duration(300)
                    .attr("stroke", l => l.type === 'version' ? CYBER_COLORS.neon.versionLink : CYBER_COLORS.linkDefault)
                    .attr("stroke-opacity", l => l.type === 'version' ? 0.6 : 0.3)
                    .attr("stroke-width", l => l.type === 'version' ? 1.5 : (0.5 + (l.rank_score || 0) * 2));
                label.transition().duration(300).style("opacity", d => {
                    if (d.group === 'concept') return 1;
                    return 0; // Restore default hidden state for docs
                });
            });

        // Click Handler (Nodes)
        node.on("click", (e, d) => {
            e.stopPropagation();
            setSelectedNodeId(d.id);

            if (d.group === 'document') {
                if (onDocClick) onDocClick(d.id);
            } else if (d.group === 'concept') {
                // [Modified] 3-Hop Cascade Subgraph Expansion
                setLoading(true);
                AIService.getGraphSubgraph({
                    center_concept_id: d.id,
                    mode: 'cascade',
                    doc_limit: 20,
                    concepts_per_doc: 6,
                    docs_per_concept: 5,
                    max_total_nodes: 600,
                    max_total_edges: 1200
                }).then(res => {
                    setLoading(false);
                    if (res && res.nodes && res.nodes.length > 0) {

                        if (viewMode === 'local') {
                            // [Local Focus Mode] REPLACE graph with new 3-hop subgraph
                            const newSimNodes = res.nodes.map(n => ({ ...n, data: n, degree: 1 })) as SimulationNode[];
                            const newSimLinks = (res.links || (res as any).edges).map((l: any) => ({ ...l })) as SimulationLink[];

                            // Degree Recalc
                            const degreeMap: Record<string, number> = {};
                            newSimLinks.forEach(l => {
                                const s = typeof l.source === 'string' ? l.source : (l.source as any).id;
                                const t = typeof l.target === 'string' ? l.target : (l.target as any).id;
                                degreeMap[s] = (degreeMap[s] || 0) + 1;
                                degreeMap[t] = (degreeMap[t] || 0) + 1;
                            });
                            newSimNodes.forEach(n => { n.degree = degreeMap[n.id] || 1; });

                            setRawNodes(newSimNodes);
                            setRawLinks(newSimLinks);

                            // Centering
                            if (zoomRef.current && svgRef.current) {
                                d3.select(svgRef.current)
                                    .transition().duration(750)
                                    .call(zoomRef.current.transform,
                                        d3.zoomIdentity.translate(dimensions.width / 2, dimensions.height / 2).scale(0.9));
                            }

                        } else {
                            // [Default Mode] MERGE (Expand)
                            setRawNodes(prevNodes => {
                                const nodeMap = new Map<string, SimulationNode>();
                                prevNodes.forEach(n => nodeMap.set(n.id, n));

                                // Append new nodes
                                res.nodes.forEach(n => {
                                    if (!nodeMap.has(n.id)) {
                                        nodeMap.set(n.id, { ...n, data: n, degree: 1, x: d.x, y: d.y } as SimulationNode); // Spawn near parent
                                    }
                                });
                                return Array.from(nodeMap.values());
                            });

                            setRawLinks(prevLinks => {
                                const linkMap = new Map<string, SimulationLink>();
                                // Existing links
                                prevLinks.forEach(l => {
                                    const s = typeof l.source === 'string' ? l.source : (l.source as any).id;
                                    const t = typeof l.target === 'string' ? l.target : (l.target as any).id;
                                    const k = `${s}|${t}|${l.type}`;
                                    linkMap.set(k, l);
                                });

                                // New links
                                const newRawLinks = res.links || (res as any).edges || [];
                                newRawLinks.forEach((l: any) => {
                                    const s = l.source;
                                    const t = l.target;
                                    const k = `${s}|${t}|${l.type || 'related'}`; // Fix potential key mismatch
                                    if (!linkMap.has(k)) {
                                        linkMap.set(k, { ...l } as SimulationLink);
                                    }
                                });
                                return Array.from(linkMap.values());
                            });
                        }

                        // Note: Simulation auto-restarts on prop change in useEffect
                    }
                }).catch(err => {
                    setLoading(false);
                    console.error("Cascade Expand Error:", err);
                });
            }
        });

        // Tick
        simulation.on("tick", () => {
            link.attr("x1", d => (d.source as SimulationNode).x!)
                .attr("y1", d => (d.source as SimulationNode).y!)
                .attr("x2", d => (d.target as SimulationNode).x!)
                .attr("y2", d => (d.target as SimulationNode).y!);
            node.attr("transform", d => `translate(${d.x},${d.y})`);
            label.attr("transform", d => `translate(${d.x},${d.y})`);
        });

        return () => { simulation.stop(); };

    }, [groupedNodes, groupedLinks, dimensions, onDocClick]);

    // Controls
    const handleZoomIn = () => zoomRef.current && svgRef.current && d3.select(svgRef.current).call(zoomRef.current.scaleBy, 1.3);
    const handleZoomOut = () => zoomRef.current && svgRef.current && d3.select(svgRef.current).call(zoomRef.current.scaleBy, 0.7);
    const handleReset = () => zoomRef.current && svgRef.current && d3.select(svgRef.current).call(zoomRef.current.transform, d3.zoomIdentity.translate(dimensions.width / 2, dimensions.height / 2).scale(0.8));

    return (
        <div ref={containerRef} className="h-full flex flex-col relative overflow-hidden" style={{ background: CYBER_COLORS.backgroundGradient }}>
            <div className="absolute inset-0 pointer-events-none z-[1]" style={{ background: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px)', mixBlendMode: 'overlay' }} />

            {/* Header / Stats */}
            <div className="absolute top-4 left-4 z-20 flex flex-col gap-2">
                <div className="bg-black/70 backdrop-blur-xl px-4 py-2.5 rounded-xl border border-cyan-500/20 flex items-center gap-3 shadow-2xl">
                    <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg">
                        <Network size={18} className="text-white" />
                    </div>
                    <div>
                        <div className="text-sm font-bold text-white">Knowledge Graph</div>
                        <div className="text-[10px] text-cyan-300/70 font-mono">{stats.nodes} nodes · {stats.links} edges</div>
                    </div>
                </div>
                {/* View Controls */}
                <div className="bg-black/60 backdrop-blur-md px-2 py-2 rounded-lg border border-white/10 flex flex-col gap-2">
                    {/* Mode Select */}
                    <div className="flex items-center gap-2 px-1">
                        <span className="text-[10px] text-slate-400 uppercase font-bold tracking-wider">Mode</span>
                        <select
                            value={viewMode}
                            onChange={(e) => setViewMode(e.target.value as 'default' | 'local')}
                            className="bg-black/50 text-white text-xs border border-white/10 rounded px-2 py-1 outline-none focus:border-cyan-500"
                        >
                            <option value="default">Default (Expand)</option>
                            <option value="local">Local Focus</option>
                        </select>
                    </div>

                    <div className="h-px bg-white/10 w-full" />

                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setShowRestricted(!showRestricted)}
                            className={`p-1.5 rounded-md transition-all flex items-center gap-1.5 text-[10px] font-bold ${showRestricted ? 'bg-red-900/50 text-red-200 border border-red-500/30' : 'text-slate-400 hover:bg-white/10'}`}
                        >
                            <Target size={12} />
                            Restricted
                        </button>
                    </div>
                </div>
            </div>

            {/* Zoom Controls */}
            <div className="absolute bottom-6 right-6 z-20 flex flex-col gap-1.5">
                <button onClick={handleZoomIn} className="w-10 h-10 bg-black/70 rounded-lg border border-white/10 text-cyan-400 hover:bg-cyan-500/10 flex items-center justify-center"><Plus size={18} /></button>
                <button onClick={handleZoomOut} className="w-10 h-10 bg-black/70 rounded-lg border border-white/10 text-cyan-400 hover:bg-cyan-500/10 flex items-center justify-center"><Minus size={18} /></button>
                <button onClick={handleReset} className="w-10 h-10 bg-black/70 rounded-lg border border-white/10 text-cyan-400 hover:bg-cyan-500/10 flex items-center justify-center"><Crosshair size={18} /></button>
                <div className="h-2" />
                <button onClick={() => loadInit()} className="w-10 h-10 bg-black/70 rounded-lg border border-white/10 text-emerald-400 hover:bg-emerald-500/10 flex items-center justify-center"><RefreshCw size={18} className={loading ? "animate-spin" : ""} /></button>
            </div>

            <div className="flex-1 w-full h-full z-10">
                <svg ref={svgRef} className="w-full h-full block" />
            </div>
        </div >
    );
};

export default KnowledgeGraph;
