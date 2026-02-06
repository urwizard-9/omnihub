import React, { useEffect, useState, useRef } from 'react';
import { AIService } from '../../services/aiService';
import { GraphData, GraphNode } from '../../types';
import { Network, ZoomIn, Loader2, Zap } from 'lucide-react'; // Added Zap, Loader2
import { useOmniHub } from '../../context/OmniHubContext'; // Import hook

const KnowledgeGraph: React.FC = () => {
    const { aiStatus } = useOmniHub(); // Consume context
    const [graph, setGraph] = useState<GraphData>({ nodes: [], links: [] });
    const [loading, setLoading] = useState(false);

    // Initial Load & Live Polling Logic
    useEffect(() => {
        loadInit();

        let interval: NodeJS.Timeout;
        if (aiStatus === 'analyzing') {
            // Live Polling during Phase B
            interval = setInterval(() => {
                loadInit(true); // Silent update
            }, 5000);
        }

        return () => {
            if (interval) clearInterval(interval);
        };
    }, [aiStatus]);

    const loadInit = async (silent = false) => {
        if (!silent) setLoading(true);
        try {
            const data = await AIService.getGraphInit(20);

            // Defensive check for data integrity
            if (data && (data.nodes || data.links)) {
                setGraph(prev => {
                    // Simple merge strategy or replacement? 
                    // For 'Live' feel, replacement is okay if nodes are stable, 
                    // but D3/ForceGraph usually handles diffs. 
                    // Here we just replace data and let the renderer handle it.
                    return data;
                });
            }
        } catch (e) {
            console.error(e);
        } finally {
            if (!silent) setLoading(false);
        }
    };

    const handleNodeClick = async (node: GraphNode) => {
        if (node.group !== 'concept') return;
        try {
            const extra = await AIService.expandGraph(node.id, 'concept');
            setGraph(prev => ({
                nodes: [...prev.nodes, ...extra.nodes.filter(n => !prev.nodes.find(pn => pn.id === n.id))],
                links: [...prev.links, ...extra.links]
            }));
        } catch (e) {
            console.error(e);
        }
    };

    return (
        <div className="h-full bg-[#09090b] flex flex-col relative overflow-hidden">
            <div className="absolute top-4 left-4 z-10 flex gap-2">
                <div className="bg-black/50 backdrop-blur px-3 py-1.5 rounded-full border border-white/10 text-xs text-slate-400 flex items-center gap-2">
                    <Network size={14} className="text-indigo-500" />
                    <span>Knowledge Graph (Beta)</span>
                </div>

                {/* Live Generation Indicator */}
                {aiStatus === 'analyzing' && (
                    <div className="bg-amber-500/10 backdrop-blur px-3 py-1.5 rounded-full border border-amber-500/20 text-xs text-amber-300 flex items-center gap-2 animate-pulse shadow-[0_0_15px_rgba(245,158,11,0.2)]">
                        <Zap size={14} className="fill-amber-500 text-amber-500" />
                        <span className="font-bold tracking-wide">AI GENERATING NODES...</span>
                    </div>
                )}
            </div>

            <div className="flex-1 flex items-center justify-center relative">
                {loading && graph.nodes.length === 0 && (
                    <div className="text-indigo-500 animate-pulse">Initializing Graph...</div>
                )}

                {/* Simple SVG Visualization Placeholder */}
                <svg width="100%" height="100%" className="opacity-80">
                    <defs>
                        <marker id="arrow" markerWidth="10" markerHeight="10" refX="15" refY="3" orient="auto" markerUnits="strokeWidth">
                            <path d="M0,0 L0,6 L9,3 z" fill="#4f46e5" />
                        </marker>
                    </defs>
                    {graph.links?.map((link, i) => {
                        // Random positions for demo (In real app, use D3 simulation)
                        // This is just a visual placeholders if no position data
                        const sx = Math.random() * 800;
                        const sy = Math.random() * 600;
                        const tx = Math.random() * 800;
                        const ty = Math.random() * 600;
                        return (
                            <line key={i} x1={sx} y1={sy} x2={tx} y2={ty} stroke="#334155" strokeWidth="1" />
                        );
                    })}
                    {graph.nodes?.map((node, i) => {
                        // Random positions
                        const cx = 100 + Math.random() * 600;
                        const cy = 100 + Math.random() * 400;
                        return (
                            <g key={node.id} onClick={() => handleNodeClick(node)} className="cursor-pointer hover:opacity-80 transition-opacity">
                                <circle
                                    cx={cx} cy={cy}
                                    r={node.group === 'concept' ? 8 : 5}
                                    fill={node.group === 'concept' ? '#6366f1' : '#10b981'}
                                    className="drop-shadow-lg"
                                />
                                <text x={cx + 12} y={cy + 4} fill="white" fontSize="10" className="pointer-events-none select-none">
                                    {node.label || node.id}
                                </text>
                            </g>
                        );
                    })}
                </svg>

                <div className="absolute bottom-4 right-4 text-[10px] text-slate-600">
                    * Visualization is static placeholder for demo
                </div>
            </div>
        </div>
    );
};

export default KnowledgeGraph;
