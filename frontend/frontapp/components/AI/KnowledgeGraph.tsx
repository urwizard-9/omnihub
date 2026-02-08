import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import * as d3 from 'd3';
import { AIService } from '../../services/aiService';
import { groupDocsByVersion, getVersionRangeText, extractVersionMeta } from '../../services/dataService';
import { DocRecord } from '../../types';
import { Network, Zap, RefreshCw, Minus, Plus, Target, Crosshair, Layers, FolderOpen } from 'lucide-react';
import { useOmniHub } from '../../context/OmniHubContext';

// ========== 타입 정의 ==========
interface KnowledgeGraphProps {
    onDocClick?: (docId: string) => void;
}

interface SimulationNode extends d3.SimulationNodeDatum {
    id: string;
    label?: string;
    group?: 'document' | 'concept' | 'group' | 'virtualPath';
    type?: string;
    mentions?: number;
    size?: number;
    degree?: number;
    // 추가 속성
    data?: any; // 원본 DocRecord 등
    isVersionChild?: boolean;
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
    if (d.group === 'group') return CYBER_COLORS.neon.group;
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
    if (d.group === 'group') return 24;
    const baseDegree = d.degree || 1;
    if (d.group === 'document') {
        if (d.isVersionChild) return 10;
        return Math.min(5 + Math.sqrt(baseDegree) * 2, 14);
    }
    return Math.min(8 + Math.sqrt(baseDegree) * 3, 32);
};

const getFontSize = (d: SimulationNode): number => {
    if (d.group === 'group') return 12;
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
    const [groupByVersion, setGroupByVersion] = useState(true);
    const [expandedGroups, setExpandedGroups] = useState<string[]>([]);

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
            const data = await AIService.getGraphInit(50, 'overview');
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

    // ========== 데이터 그룹화 로직 (Memoized) ==========
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

        if (!groupByVersion) {
            return { nodes: filteredNodes, links: filteredLinks };
        }

        // 3. Grouping & Virtual Paths
        const docNodes: DocRecord[] = [];
        const otherNodes: SimulationNode[] = [];
        const docNodeMap: Record<string, SimulationNode> = {};
        const folderPaths = new Set<string>();

        filteredNodes.forEach(n => {
            if (n.group === 'document') {
                const rawData = n.data || {};
                const safeName = rawData.name || n.label || n.id || "Untitled";
                const doc: DocRecord = {
                    ...rawData,
                    id: n.id,
                    name: safeName,
                    // ... (rest of fields are safety-filled via n.data usually)
                    folderPath: rawData.folderPath || '',
                    security: rawData.security || 'medium'
                } as any; // Cast for brevity, real app has full object

                docNodes.push(doc);
                docNodeMap[n.id] = n;
                if (doc.folderPath) folderPaths.add(doc.folderPath);
            } else {
                otherNodes.push(n);
            }
        });

        // 3.1. Create Virtual Path Nodes
        const folderNodes: SimulationNode[] = [];
        // Optional: Create hierarchy (parent folders). For now, just leaf folders mentioned in docs.
        folderPaths.forEach(path => {
            const folderId = `folder:${path}`;
            folderNodes.push({
                id: folderId,
                label: path.split('/').pop() || path,
                group: 'virtualPath',
                data: { fullPath: path },
                degree: 0
            });
        });

        // 3.2. Group Docs
        const { groups, singles } = groupDocsByVersion(docNodes);
        const finalNodes: SimulationNode[] = [...otherNodes, ...folderNodes];
        const docIdToGroupId: Record<string, string> = {};

        // Singles
        singles.forEach(d => {
            finalNodes.push({
                ...docNodeMap[d.id],
                id: d.id, label: d.name, group: 'document', data: d
            });
            docIdToGroupId[d.id] = d.id;
        });

        // Groups
        Object.entries(groups).forEach(([groupKey, docList]) => {
            const groupId = `group:${groupKey}`;
            const isExpanded = expandedGroups.includes(groupKey);
            const representative = docList[0];
            const versionText = getVersionRangeText(docList);
            const hasSSOT = docList.some(d => d.ssotRating);

            const groupNode: SimulationNode = {
                id: groupId,
                label: isExpanded ? `📚 ${groupKey}` : `📚 ${groupKey} (x${docList.length})`,
                group: 'group',
                data: { groupKey, count: docList.length, representative, versionRangeText: versionText, hasSSOT, isExpanded, folderPath: representative.folderPath },
                x: docNodeMap[representative.id]?.x,
                y: docNodeMap[representative.id]?.y,
                degree: docList.length
            };
            finalNodes.push(groupNode);

            docList.forEach(d => docIdToGroupId[d.id] = groupId);

            if (isExpanded) {
                docList.slice(0, 12).forEach((d, i) => {
                    const meta = extractVersionMeta(d.name);
                    let label = versionText; // Simplify
                    if (meta.versionNumber) label = `v${meta.versionNumber}`;

                    finalNodes.push({
                        id: d.id,
                        label: label,
                        group: 'document',
                        isVersionChild: true,
                        data: d,
                        x: (groupNode.x || 0) + Math.cos(i) * 30,
                        y: (groupNode.y || 0) + Math.sin(i) * 30
                    });
                });
            }
        });

        // 3.3. Process Links (Original + Virtual Path Links)
        const finalLinks: SimulationLink[] = [];
        const linkDedup = new Set<string>();

        // Original Links
        filteredLinks.forEach(link => {
            const sourceId = typeof link.source === 'string' ? link.source : (link.source as any).id;
            const targetId = typeof link.target === 'string' ? link.target : (link.target as any).id;

            const newSource = docIdToGroupId[sourceId] || sourceId;
            const newTarget = docIdToGroupId[targetId] || targetId;

            if (newSource !== newTarget && !linkDedup.has(`${newSource}-${newTarget}`)) {
                linkDedup.add(`${newSource}-${newTarget}`);
                finalLinks.push({
                    source: newSource, target: newTarget,
                    type: 'related',
                    rank_score: link.rank_score
                });
            }
        });

        // Group -> Child Links
        Object.entries(groups).forEach(([groupKey, docList]) => {
            if (expandedGroups.includes(groupKey)) {
                const groupId = `group:${groupKey}`;
                docList.slice(0, 12).forEach(d => {
                    finalLinks.push({ source: groupId, target: d.id, type: 'version' });
                });
            }
        });

        // Feature: Link Docs/Groups to Virtual Folders
        // Iterate Nodes to find docs/groups with folderPath and link to folderNode
        // We do this by iterating finalNodes to see if they have data.folderPath
        finalNodes.forEach(n => {
            if ((n.group === 'document' && !n.isVersionChild) || n.group === 'group') {
                const fPath = n.data?.folderPath;
                if (fPath) {
                    const folderId = `folder:${fPath}`;
                    // Check if folder node exists (it should)
                    if (folderNodes.find(fn => fn.id === folderId)) {
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
            }
        });

        return { nodes: finalNodes, links: finalLinks };
    }, [rawNodes, rawLinks, groupByVersion, expandedGroups, showRestricted, viewMode, selectedNodeId]);

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
                if ((d as SimulationNode).isVersionChild) return -100;
                return effectiveMode === 'default' ? -400 : -300;
            }))
            .force("collide", d3.forceCollide().radius(d => {
                const node = d as SimulationNode;
                if (node.group === 'group') return 55;
                if (node.group === 'concept') return 50;
                if (node.isVersionChild) return 25;
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
            el.append("circle").attr("r", r + 5).attr("fill", color).attr("opacity", 0.15).attr("filter", `url(#glow-${d.group === 'group' ? 'group' : 'cyan'})`);

            // Core
            el.append("circle").attr("r", r).attr("fill", `color-mix(in srgb, ${color} 20%, ${CYBER_COLORS.background})`)
                .attr("stroke", color).attr("stroke-width", d.group === 'group' ? 2 : 1.5);

            // Icon / Text
            if (d.group === 'group') {
                el.append("text").text(d.data?.isExpanded ? "📂" : "📚").attr("dy", 6).attr("text-anchor", "middle").attr("font-size", "16px");
                if (!d.data?.isExpanded && d.data?.versionRangeText) {
                    el.append("text").text(d.data.versionRangeText).attr("dy", 20).attr("text-anchor", "middle").attr("fill", CYBER_COLORS.textMuted).attr("font-size", "8px");
                }
            } else if (d.group === 'virtualPath') {
                el.append("text").text("📂").attr("dy", 5).attr("text-anchor", "middle").attr("font-size", "14px");
            }

            // SSOT Star
            if ((d.group === 'document' && d.data?.ssotRating) || (d.group === 'group' && d.data?.hasSSOT)) {
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
                // Concepts always visible
                if (d.group === 'concept' || d.group === 'group') return 1;
                // Docs hidden by default (shown on hover/zoom)
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
                    if (d.group === 'concept' || d.group === 'group') return 1;
                    return 0; // Restore default hidden state for docs
                });
            });

        // Click Handler (Nodes)
        node.on("click", (e, d) => {
            e.stopPropagation();
            setSelectedNodeId(d.id);

            if (d.group === 'group') {
                const key = d.data.groupKey;
                setExpandedGroups(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
            } else if (d.group === 'document') {
                if (onDocClick) onDocClick(d.id);
            } else if (d.group === 'concept') {
                // [Modified] Local Focus 3-Hop Expansion
                // Instead of merging, we REPLACE the graph with the expanded neighborhood.
                // This creates the "Local Focus" effect requested.
                // Passing limit=50 to get robust 3rd hop data (backend handles logic)
                setLoading(true);
                AIService.expandGraph(d.id, 'concept', 50).then(res => {
                    setLoading(false);
                    if (res && res.nodes && res.nodes.length > 0) {
                        const newSimNodes = res.nodes.map(n => ({ ...n, data: n, degree: 1 })) as SimulationNode[];
                        const newSimLinks = (res.links || (res as any).edges).map((l: any) => ({ ...l })) as SimulationLink[];

                        // Force layout restart
                        setRawNodes(newSimNodes);
                        setRawLinks(newSimLinks);

                        // Optional: Reset zoom to center
                        if (zoomRef.current && svgRef.current) {
                            d3.select(svgRef.current)
                                .transition().duration(750)
                                .call(zoomRef.current.transform,
                                    d3.zoomIdentity.translate(dimensions.width / 2, dimensions.height / 2).scale(1.0));
                        }
                    }
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
                            onClick={() => setGroupByVersion(!groupByVersion)}
                            className={`p-1.5 rounded-md transition-all flex items-center gap-1.5 text-[10px] font-bold ${groupByVersion ? 'bg-indigo-600/80 text-white' : 'text-slate-400 hover:bg-white/10'}`}
                        >
                            <Layers size={12} />
                            Versioning
                        </button>
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
        </div>
    );
};

export default KnowledgeGraph;
