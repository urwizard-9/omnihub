
import React, { useEffect, useRef, useState, useMemo } from 'react';
import * as d3 from 'd3';
import { AIService } from '../../services/aiService';
import { GraphData, GraphNode, GraphLink } from '../../types';
import { Network, Zap, ZoomIn, ZoomOut, RefreshCw } from 'lucide-react';
import { useOmniHub } from '../../context/OmniHubContext';

// D3 Simulation용 타입 확장
interface SimulationNode extends GraphNode, d3.SimulationNodeDatum { }
interface SimulationLink extends d3.SimulationLinkDatum<SimulationNode> {
    source: string | SimulationNode;
    target: string | SimulationNode;
    type?: string;
}

const KnowledgeGraph: React.FC = () => {
    const { aiStatus } = useOmniHub();
    const svgRef = useRef<SVGSVGElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    // 그래프 데이터 상태
    const [graphData, setGraphData] = useState<{ nodes: SimulationNode[], links: SimulationLink[] }>({ nodes: [], links: [] });
    const [loading, setLoading] = useState(false);
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

    // 1. 초기 데이터 로드
    useEffect(() => {
        loadInit();

        let interval: NodeJS.Timeout;
        if (aiStatus === 'analyzing') {
            interval = setInterval(() => loadInit(true), 5000); // Live Polling
        }
        return () => clearInterval(interval);
    }, [aiStatus]);

    const loadInit = async (silent = false) => {
        if (!silent) setLoading(true);
        try {
            const data = await AIService.getGraphInit(50); // Fetch top 50 nodes
            if (data && data.nodes) {
                // 기존 위치 정보를 유지하기 위해 데이터 병합 로직 필요할 수 있음
                // 여기서는 간단히 교체하되, 시뮬레이션이 안정화되도록 처리

                // Convert raw data to simulation-ready data
                // (Create new array references to avoid mutation issues in React strict mode)
                const simNodes = data.nodes.map(n => ({ ...n })) as SimulationNode[];
                const simLinks = (data.links || []).map(l => ({ ...l })) as SimulationLink[];

                setGraphData({ nodes: simNodes, links: simLinks });
            }
        } catch (e) {
            console.error("Graph Load Error:", e);
        } finally {
            if (!silent) setLoading(false);
        }
    };

    // 2. 화면 크기 감지
    useEffect(() => {
        if (!containerRef.current) return;
        const resizeObserver = new ResizeObserver((entries) => {
            if (!entries.length) return;
            const { width, height } = entries[0].contentRect;
            setDimensions({ width, height });
        });
        resizeObserver.observe(containerRef.current);
        return () => resizeObserver.disconnect();
    }, []);

    // 3. D3 렌더링 & 시뮬레이션
    useEffect(() => {
        if (!svgRef.current || dimensions.width === 0 || graphData.nodes.length === 0) return;

        const { width, height } = dimensions;
        const svg = d3.select(svgRef.current);

        // Clear previous render
        svg.selectAll("*").remove();

        // [Fix] Deep Copy for D3 Mutation (State Immutability)
        // D3 modifies nodes and links in-place (source/target strings -> object references)
        // We must pass a fresh copy to D3 on every render to avoid React state mutation issues.
        const simulationNodes = graphData.nodes.map(d => ({ ...d })) as SimulationNode[];
        const simulationLinks = graphData.links.map(d => ({ ...d })) as SimulationLink[];

        console.log("Creating Simulation with:", {
            nodes: simulationNodes.length,
            links: simulationLinks.length
        });

        // Container Group for Zoom
        const g = svg.append("g");

        // Grid Pattern Definition
        const defs = svg.append("defs");
        const pattern = defs.append("pattern")
            .attr("id", "grid-pattern")
            .attr("width", 20)
            .attr("height", 20)
            .attr("patternUnits", "userSpaceOnUse");

        pattern.append("circle")
            .attr("cx", 1)
            .attr("cy", 1)
            .attr("r", 1)
            .attr("fill", "#334155")
            .attr("opacity", 0.5);

        // Background Rect
        g.append("rect")
            .attr("width", width * 4) // 넉넉하게
            .attr("height", height * 4)
            .attr("x", -width * 1.5)
            .attr("y", -height * 1.5)
            .attr("fill", "url(#grid-pattern)")
            .attr("pointer-events", "none"); // 줌 이벤트 통과

        // Zoom Setup
        const zoom = d3.zoom<SVGSVGElement, unknown>()
            .scaleExtent([0.1, 4])
            .on("zoom", (event) => g.attr("transform", event.transform));
        svg.call(zoom);

        // [Debug] Data Check
        console.log("Visualizing Graph Data:", graphData);

        // --- Physics Simulation (Tuned for tighter layout) ---
        const simulation = d3.forceSimulation<SimulationNode>(simulationNodes)
            .force("link", d3.forceLink<SimulationNode, SimulationLink>(simulationLinks)
                .id(d => d.id)
                .distance(80) // 링크 길이 단축 (120 -> 80)
                .strength(0.8) // 당기는 힘 강화
            )
            .force("charge", d3.forceManyBody().strength(-250)) // 밀어내는 힘 약화 (-400 -> -200)
            .force("collide", d3.forceCollide().radius(d => (d.type === 'concept' ? 35 : 25))) // 겹침 방지 반경 확대
            .force("center", d3.forceCenter(width / 2, height / 2).strength(0.3)); // 중앙 중력 강화

        // --- Render Elements ---

        // Arrow Marker Definition
        svg.append("defs").append("marker")
            .attr("id", "arrow")
            .attr("viewBox", "0 -5 10 10")
            .attr("refX", 20) // 노드 반경에 맞춰 조정
            .attr("refY", 0)
            .attr("markerWidth", 6)
            .attr("markerHeight", 6)
            .attr("orient", "auto")
            .append("path")
            .attr("d", "M0,-5L10,0L0,5")
            .attr("fill", "#64748b"); // Slate-500

        // Links (Dashed Style)
        const link = g.append("g")
            .attr("stroke", "#94a3b8")
            .attr("stroke-opacity", 0.6)
            .selectAll("line")
            .data(simulationLinks) // [Using Copied Data]
            .join("line")
            .attr("stroke-width", 1.5)
            .attr("stroke-dasharray", "3,3"); // 점선 효과
        // .attr("marker-end", "url(#arrow)"); // 화살표 (선택 사항)

        // Nodes
        const node = g.append("g")
            .selectAll("g")
            .data(simulationNodes) // [Using Copied Data]
            .join("g")
            .attr("cursor", "pointer")
            .on("click", (event, d) => handleNodeClick(d)); // Node Click Handler

        // Node Circles (Hollow Style)
        node.append("circle")
            .attr("r", d => d.type === 'concept' ? 12 : 8) // 크기 확대
            .attr("fill", "#09090b") // 내부 검정 (배경색과 동일)
            .attr("stroke", d => {
                if (d.type === 'concept') return '#4ade80'; // Bright Green
                if (d.type === 'document') return '#60a5fa'; // Bright Blue
                return '#94a3b8';
            })
            .attr("stroke-width", 2);

        // Node Labels (Better Typography)
        node.append("text")
            .text(d => d.label || d.id)
            .attr("x", 16)
            .attr("y", 5)
            .attr("fill", "#e2e8f0")
            .attr("font-size", "11px")
            .attr("font-family", "monospace") // Tech feel
            .attr("stroke", "none")
            .attr("pointer-events", "none")
            .style("text-shadow", "0 0 3px #000"); // 텍스트 가독성

        // Drag Interaction
        const drag = d3.drag<SVGGElement, SimulationNode>()
            .on("start", (event, d) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on("drag", (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
            })
            .on("end", (event, d) => {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            });

        node.call(drag as any);

        // Simulation Tick
        simulation.on("tick", () => {
            link
                .attr("x1", d => (d.source as SimulationNode).x!)
                .attr("y1", d => (d.source as SimulationNode).y!)
                .attr("x2", d => (d.target as SimulationNode).x!)
                .attr("y2", d => (d.target as SimulationNode).y!);

            node.attr("transform", d => `translate(${d.x},${d.y})`);
        });

        // Cleanup
        return () => {
            simulation.stop();
        };

    }, [graphData, dimensions]);

    // Handle Node Click (Update Data)
    const handleNodeClick = async (node: SimulationNode) => {
        if (node.type !== 'concept') return; // Only expand concepts

        try {
            // Visual Feedback (e.g., spin or highlight)
            // Call API to get neighbors
            const extra = await AIService.expandGraph(node.id, 'concept');

            if (extra && extra.nodes.length > 0) {
                setGraphData(prev => {
                    // Merge constraints
                    const newNodes = [...prev.nodes];
                    const existingIds = new Set(newNodes.map(n => n.id));

                    extra.nodes.forEach(n => {
                        if (!existingIds.has(n.id)) {
                            // Spawn new nodes near the parent
                            const newNode = { ...n, x: node.x, y: node.y } as SimulationNode;
                            newNodes.push(newNode);
                        }
                    });

                    const newLinks = [...prev.links];
                    // Link deduplication logic needed ideally, simpler here:
                    const existingLinks = new Set(newLinks.map(l =>
                        `${(l.source as any).id || l.source}-${(l.target as any).id || l.target}`
                    ));

                    extra.links.forEach(l => {
                        const key = `${l.source}-${l.target}`;
                        if (!existingLinks.has(key)) {
                            newLinks.push({ ...l } as SimulationLink);
                        }
                    });

                    return { nodes: newNodes, links: newLinks };
                });
            }
        } catch (e) {
            console.error("Expand Error:", e);
        }
    };

    return (
        <div ref={containerRef} className="h-full bg-[#09090b] flex flex-col relative overflow-hidden">
            {/* Header / Toolbar */}
            <div className="absolute top-4 left-4 z-10 flex gap-2">
                <div className="bg-black/50 backdrop-blur px-3 py-1.5 rounded-full border border-white/10 text-xs text-slate-400 flex items-center gap-2">
                    <Network size={14} className="text-indigo-500" />
                    <span className="font-semibold text-slate-200">Knowledge Graph</span>
                    <span className="px-1.5 py-0.5 bg-indigo-500/20 text-indigo-400 rounded text-[10px]">Beta</span>
                </div>

                {/* Live Indicator */}
                {aiStatus === 'analyzing' && (
                    <div className="bg-amber-500/10 backdrop-blur px-3 py-1.5 rounded-full border border-amber-500/20 text-xs text-amber-300 flex items-center gap-2 animate-pulse">
                        <Zap size={14} className="fill-amber-500 text-amber-500" />
                        <span className="font-bold tracking-wide">LIVE UPDATING</span>
                    </div>
                )}
            </div>

            {/* Controls (Example) */}
            <div className="absolute bottom-6 right-6 z-10 flex flex-col gap-2">
                <button
                    onClick={() => loadInit()}
                    className="p-2 bg-slate-800/80 hover:bg-slate-700 text-white rounded-lg border border-white/10 transition-colors"
                    title="Reload Graph"
                >
                    <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
                </button>
            </div>

            {/* Helper Text */}
            <div className="absolute bottom-6 left-6 z-10 text-[10px] text-slate-500 pointer-events-none select-none">
                <div className="flex items-center gap-2 mb-1">
                    <span className="w-2 h-2 rounded-full bg-emerald-500"></span> Concept (Key Term)
                </div>
                <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-blue-500"></span> Document (File)
                </div>
            </div>

            {/* D3 SVG Container */}
            <div className="flex-1 w-full h-full cursor-move">
                {graphData.nodes.length === 0 && !loading && (
                    <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
                        No Graph Data Available
                    </div>
                )}
                <svg ref={svgRef} className="w-full h-full block" />
            </div>
        </div>
    );
};

export default KnowledgeGraph;
