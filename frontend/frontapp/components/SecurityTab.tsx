import React, { useMemo, useState } from 'react';
import { useOmniHub } from '../context/OmniHubContext';
import { ShieldCheck, Activity, BarChart3, CloudLightning, X, Search, User, AlertTriangle, CheckCircle, Clock, RefreshCcw } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, LineChart, Line } from 'recharts';
import EventLogPanel from './EventLogPanel';
import { RiskData } from '../types';
import { BackendAPI } from '../services/dataService';

const SecurityTab: React.FC = () => {
    const {
        resetSecurity,
        securityState,
        riskHistory, // This is now treated as "List of Latest User States"
        refreshRiskData // Added
    } = useOmniHub();

    const [selectedUser, setSelectedUser] = useState<RiskData | null>(null);
    const [latestSnapshot, setLatestSnapshot] = useState<RiskData | null>(null);

    const [isRefreshing, setIsRefreshing] = useState(false);

    const handleRefresh = async () => {
        if (refreshRiskData) {
            setIsRefreshing(true);
            const startTime = Date.now();

            try {
                await refreshRiskData();
            } finally {
                // Ensure minimum 500ms loading display for visual feedback
                const elapsed = Date.now() - startTime;
                const remaining = Math.max(0, 500 - elapsed);

                if (remaining > 0) {
                    await new Promise(resolve => setTimeout(resolve, remaining));
                }

                setIsRefreshing(false);
            }
        }
    };

    // 1. System Risk Trend (Mock Data for Demo with Download Failure Simulation)
    const systemTrendData = useMemo(() => {
        const data = [];
        const now = new Date();
        for (let i = 0; i < 50; i++) {
            const time = new Date(now.getTime() - (50 - i) * 5 * 60 * 1000); // 5 min interval
            let systemRisk = 0;

            if (i < 40) {
                // Normal State (Quiet)
                const baseRisk = 12;
                const noise = Math.random() * 5;
                systemRisk = baseRisk + noise;
            } else if (i < 45) {
                // Warning Signs
                systemRisk = 25 + (i - 40) * 8 + (Math.random() * 5);
            } else if (i < 49) {
                // Massive Anomaly (Download Spike)
                systemRisk = 75 + (i - 45) * 5 + (Math.random() * 3);
            } else {
                // Peak (Last point)
                systemRisk = 98;
            }

            data.push({
                time: time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                systemRisk: Math.min(100, systemRisk)
            });
        }
        return data;
    }, []);

    const isSystemAtRisk = useMemo(() => {
        if (systemTrendData.length === 0) return false;
        return systemTrendData[systemTrendData.length - 1].systemRisk > 80;
    }, [systemTrendData]);

    // 2. User Detail History State
    const [userHistoryData, setUserHistoryData] = useState<any[]>([]);

    // Fetch History when User Selected
    React.useEffect(() => {
        if (!selectedUser) {
            setUserHistoryData([]);
            setLatestSnapshot(null);
            return;
        }

        const loadHistory = async () => {
            // 1. Fetch Real History from API
            const token = localStorage.getItem('omnihub_token') || "";
            // We need to import BackendAPI (add import at top if missing, or use useOmniHub context if exposed?)
            // For now, let's assume BackendAPI is imported. Wait, it's not.
            // Let's use the fetchUserRiskHistory from useOmniHub? No, it's not exposed there yet.
            // We should import { BackendAPI } from '../services/dataService';

            // Dynamic import to avoid top-level issues if needed, or just standard import.
            // Standard import is better. I will add it in next step. For now logic:

            const history = await BackendAPI.fetchUserRiskHistory(selectedUser.userId, token);

            let historyData = history || []; // Ensure array

            // Extract latest snapshot for current state display
            const latest = historyData.length > 0 ? historyData[0] : null;
            setLatestSnapshot(latest);

            // [FALLBACK] If no history exists yet (old data before patch), use the current Snapshot as the only point.
            // This ensures the chart isn't empty for existing users.
            if (historyData.length === 0 && selectedUser) {
                console.log("No history found, falling back to current user snapshot", selectedUser);
                // Construct a synthetic history item from selectedUser
                const snapshotTime = selectedUser.lastEventAt || new Date().toISOString();
                historyData = [{
                    ...selectedUser,
                    lastEventAt: snapshotTime,
                    reconError: selectedUser.reconError || 0,
                    p95Threshold: selectedUser.p95Threshold || 0.25
                }];
                setLatestSnapshot(historyData[0]);
            }

            // 2. Process Data for Chart
            // Reverse to show oldest -> newest
            const sortedHistory = [...historyData].sort((a, b) => new Date(a.lastEventAt).getTime() - new Date(b.lastEventAt).getTime());

            let chartData = sortedHistory.map(item => ({
                time: new Date(item.lastEventAt).toLocaleTimeString([], { minute: '2-digit', second: '2-digit' }), // Show MM:SS
                error: item.reconError,
                threshold: item.p95Threshold
            }));

            // [Smart UX] If only 1 point (Cold Start), prepend a synthetic "Start" point to show a rising line.
            // Visual:  (T-10s, 0) ----> (T-0s, CurrentError)
            if (chartData.length === 1) {
                const current = chartData[0];
                const currentTime = new Date(sortedHistory[0].lastEventAt).getTime();
                const startTime = new Date(currentTime - 10000); // 10 sec ago

                chartData = [
                    {
                        time: startTime.toLocaleTimeString([], { minute: '2-digit', second: '2-digit' }),
                        error: 0,
                        threshold: current.threshold
                    },
                    current
                ];
            }

            setUserHistoryData(chartData);
        };

        loadHistory();
    }, [selectedUser]);

    return (
        <div className="flex-1 overflow-y-auto p-4 md:p-8 bg-[#09090b] scrollbar-thin relative">
            <div className="max-w-[1600px] mx-auto space-y-8">

                {/* Header */}
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                    <div>
                        <h2 className="text-3xl font-bold text-white flex items-center gap-3">
                            <ShieldCheck className="text-indigo-400" size={32} />
                            Security Ops Center
                        </h2>
                    </div>
                </div>

                {/* Top Section: System Trend & Live Feed */}
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[400px]">

                    {/* System Risk Trend */}
                    <div className="lg:col-span-2 bg-[#1E1F2E]/60 backdrop-blur border border-white/5 p-6 rounded-2xl flex flex-col">
                        <div className="flex items-center justify-between mb-6">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-indigo-500/10 rounded-lg">
                                    <Activity className="text-indigo-400" size={20} />
                                </div>
                                <div>
                                    <h3 className="text-lg font-bold text-slate-200">System Risk Overview</h3>
                                    <p className="text-xs text-slate-500">Global Risk Score (5-min Interval)</p>
                                </div>
                            </div>
                            {isSystemAtRisk ? (
                                <div className="px-3 py-1 bg-red-500/10 text-red-400 text-xs font-bold rounded-full border border-red-500/20 animate-pulse">
                                    RISK DETECTED
                                </div>
                            ) : (
                                <div className="px-3 py-1 bg-emerald-500/10 text-emerald-400 text-xs font-bold rounded-full border border-emerald-500/20">
                                    SYSTEM NORMAL
                                </div>
                            )}
                        </div>

                        <div className="flex-1 w-full min-h-0">
                            <ResponsiveContainer width="100%" height="100%">
                                <AreaChart data={systemTrendData}>
                                    <defs>
                                        <linearGradient id="colorSystemRisk" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                                            <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} opacity={0.3} />
                                    <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 10 }} tickMargin={10} minTickGap={30} axisLine={false} tickLine={false} />
                                    <YAxis stroke="#64748b" tick={{ fontSize: 10 }} domain={[0, 100]} axisLine={false} tickLine={false} />
                                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', color: '#f1f5f9' }} itemStyle={{ color: '#818cf8' }} />
                                    <Area type="monotone" dataKey="systemRisk" stroke="#6366f1" fill="url(#colorSystemRisk)" strokeWidth={3} />
                                </AreaChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    {/* Live Event Feed (Existing Component) */}
                    <div className="bg-[#1E1F2E]/60 backdrop-blur border border-white/5 rounded-2xl flex flex-col overflow-hidden">
                        <EventLogPanel />
                    </div>
                </div>

                {/* User Risk Grid */}
                <div>
                    <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
                        <User className="text-slate-400" />
                        Monitored Users
                        <span className="text-sm font-normal text-slate-500 ml-2">({riskHistory.length} Active)</span>
                        <button
                            onClick={handleRefresh}
                            className="ml-auto p-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition-colors"
                            title="Refresh User List"
                            disabled={isRefreshing}
                        >
                            <RefreshCcw size={16} className={isRefreshing ? "animate-spin" : ""} />
                        </button>
                    </h3>

                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                        {riskHistory.map((user, idx) => (
                            <div
                                key={user.userId || idx}
                                onClick={() => setSelectedUser(user)}
                                className="bg-[#1E1F2E]/40 border border-white/5 p-4 rounded-xl hover:bg-[#1E1F2E]/80 hover:border-indigo-500/30 transition-all cursor-pointer group"
                            >
                                <div className="flex justify-between items-start mb-3">
                                    <div className="flex items-center gap-3">
                                        <div className="w-10 h-10 rounded-full bg-slate-700/50 flex items-center justify-center text-slate-300 font-bold">
                                            {user.userId ? user.userId.substring(0, 2).toUpperCase() : 'U'}
                                        </div>
                                        <div>
                                            <div className="text-slate-200 font-bold text-sm truncate max-w-[120px]">{user.userId}</div>
                                            <div className="text-slate-500 text-xs">{new Date(user.lastEventAt).toLocaleTimeString()}</div>
                                        </div>
                                    </div>
                                    <div className={`px-2 py-0.5 rounded text-[10px] font-bold border ${user.defconMode === 'ALERT' ? 'bg-red-500/20 text-red-300 border-red-500/30' : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'}`}>
                                        {user.defconMode}
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <div className="flex justify-between text-xs">
                                        <span className="text-slate-500">Risk Score</span>
                                        <span className={`font-mono font-bold ${user.riskScore > 50 ? 'text-red-400' : 'text-emerald-400'}`}>
                                            {user.riskScore.toFixed(0)}
                                        </span>
                                    </div>
                                    <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                                        <div
                                            className={`h-full rounded-full ${user.riskScore > 50 ? 'bg-red-500' : 'bg-emerald-500'}`}
                                            style={{ width: `${Math.min(100, user.riskScore)}%` }}
                                        />
                                    </div>
                                    <div className="flex justify-between text-xs pt-1">
                                        <span className="text-slate-500">Anomaly Error</span>
                                        <span className="font-mono text-slate-300">{user.reconError?.toFixed(3) || '0.000'}</span>
                                    </div>
                                </div>
                            </div>
                        ))}

                        {/* Empty State */}
                        {riskHistory.length === 0 && (
                            <div className="col-span-full py-12 text-center text-slate-500 border border-dashed border-white/5 rounded-xl">
                                No active users detected
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* User Detail Modal */}
            {selectedUser && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setSelectedUser(null)}>
                    <div
                        className="bg-[#18181b] border border-white/10 w-full max-w-4xl max-h-[90vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col"
                        onClick={e => e.stopPropagation()}
                    >
                        {/* Modal Header */}
                        <div className="p-6 border-b border-white/5 flex justify-between items-center bg-[#1E1F2E]/50">
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 rounded-full bg-indigo-500/20 flex items-center justify-center text-indigo-300 font-bold text-lg border border-indigo-500/30">
                                    {selectedUser.userId.substring(0, 2).toUpperCase()}
                                </div>
                                <div>
                                    <h3 className="text-xl font-bold text-white mb-0.5">{selectedUser.userId}</h3>
                                    <p className="text-sm text-slate-400 flex items-center gap-2">
                                        <Clock size={12} />
                                        Last Updated: {new Date(latestSnapshot?.lastEventAt || selectedUser.lastEventAt).toLocaleString()}
                                    </p>
                                </div>
                            </div>
                            <button onClick={() => setSelectedUser(null)} className="text-slate-400 hover:text-white transition-colors">
                                <X size={24} />
                            </button>
                        </div>

                        {/* Modal Body */}
                        <div className="p-6 overflow-y-auto custom-scrollbar">

                            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                                {/* Left Col: Gauge & Info */}
                                <div className="space-y-6">
                                    {/* 1. Gauge: Replaced with robust SVG implementation */}
                                    <div className="bg-[#09090b] border border-white/5 p-6 rounded-xl flex flex-col items-center justify-center relative min-h-[250px]">
                                        <div className="relative w-full max-w-[240px] aspect-[2/1] flex items-end justify-center">
                                            <svg viewBox="0 0 200 100" className="w-full h-full">
                                                {/* Background Arc - gray track */}
                                                <path
                                                    d="M 20 100 A 80 80 0 0 1 180 100"
                                                    fill="none"
                                                    stroke="#1E1F2E"
                                                    strokeWidth="20"
                                                    strokeLinecap="round"
                                                />
                                                {/* Progress Arc - colored */}
                                                <path
                                                    d="M 20 100 A 80 80 0 0 1 180 100"
                                                    fill="none"
                                                    stroke={(latestSnapshot?.defconMode || selectedUser.defconMode) === 'ALERT' ? '#ef4444' : '#10b981'}
                                                    strokeWidth="20"
                                                    strokeLinecap="round"
                                                    strokeDasharray={251.2} // PI * 80 (approx circumference of semi-circle)
                                                    strokeDashoffset={251.2 * (1 - Math.max(0, Math.min(100, latestSnapshot?.riskScore ?? selectedUser.riskScore)) / 100)}
                                                    className="transition-all duration-1000 ease-out"
                                                />
                                            </svg>

                                            {/* Score Text - Positioned absolutely at bottom center of the SVG area */}
                                            <div className="absolute bottom-0 text-center mb-4">
                                                <div className="text-5xl font-black text-white leading-none">
                                                    {(latestSnapshot?.riskScore ?? selectedUser.riskScore).toFixed(0)}
                                                </div>
                                            </div>
                                        </div>
                                        <div className="mt-4 text-sm text-slate-500 font-bold uppercase tracking-wider text-center">
                                            Current Risk Score
                                        </div>
                                    </div>

                                    {/* 2. Status Badge */}
                                    <div className={`p-4 rounded-xl border flex items-center gap-4 ${(latestSnapshot?.defconMode || selectedUser.defconMode) === 'ALERT'
                                        ? 'bg-red-500/10 border-red-500/30 text-red-200'
                                        : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-200'
                                        }`}>
                                        {(latestSnapshot?.defconMode || selectedUser.defconMode) === 'ALERT' ? <AlertTriangle size={24} /> : <CheckCircle size={24} />}
                                        <div>
                                            <div className="text-xs font-bold opacity-70 uppercase">Security Status</div>
                                            <div className="text-xl font-bold tracking-wide">{latestSnapshot?.defconMode || selectedUser.defconMode}</div>
                                        </div>
                                    </div>
                                </div>

                                {/* Right Col: Detail Chart & Metadata */}
                                <div className="lg:col-span-2 space-y-6">
                                    {/* Real History Chart for User */}
                                    <div className="bg-[#09090b] border border-white/5 p-6 rounded-xl h-[300px] flex flex-col">
                                        <h4 className="text-sm font-bold text-slate-400 mb-4 flex items-center gap-2">
                                            <Activity size={16} /> User Anomaly Deviation (Real-time History)
                                        </h4>
                                        <div className="flex-1 w-full min-h-0">
                                            {userHistoryData.length > 0 ? (
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <LineChart data={userHistoryData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                                                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.2} vertical={false} />
                                                        <XAxis
                                                            dataKey="time"
                                                            tick={{ fontSize: 10, fill: '#64748b' }}
                                                            minTickGap={30}
                                                            tickMargin={10}
                                                            stroke="#334155"
                                                        />
                                                        <YAxis
                                                            stroke="#64748b"
                                                            tick={{ fontSize: 10 }}
                                                            domain={[0, 'auto']}
                                                            allowDataOverflow={false}
                                                            tickMargin={10}
                                                            strokeWidth={0}
                                                        />
                                                        <Tooltip
                                                            contentStyle={{ backgroundColor: '#18181b', border: '1px solid #333' }}
                                                            itemStyle={{ color: '#fff' }}
                                                        />
                                                        <Line
                                                            type="monotone"
                                                            dataKey="error"
                                                            stroke="#ef4444"
                                                            strokeWidth={3}
                                                            dot={{ r: 4, fill: '#ef4444', strokeWidth: 0 }}
                                                            activeDot={{ r: 6, fill: '#fff' }}
                                                            isAnimationActive={false} // Disable animation to prevent "empty on load" flickering
                                                        />
                                                        <Line
                                                            type="monotone"
                                                            dataKey="threshold"
                                                            stroke="#3b82f6"
                                                            strokeDasharray="4 4"
                                                            dot={false}
                                                            strokeWidth={2}
                                                            isAnimationActive={false}
                                                        />
                                                    </LineChart>
                                                </ResponsiveContainer>
                                            ) : (
                                                <div className="flex items-center justify-center h-full text-slate-500 text-sm">
                                                    No history data available
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* Metadata Grid */}
                                    <div className="bg-[#09090b] border border-white/5 p-6 rounded-xl">
                                        <h4 className="text-sm font-bold text-slate-400 mb-4 flex items-center gap-2">
                                            <CloudLightning size={16} /> Risk Analysis Metadata
                                        </h4>
                                        <div className="grid grid-cols-2 gap-y-4 gap-x-8 text-sm">
                                            <div>
                                                <span className="text-slate-500 block text-xs">Reconstruction Error</span>
                                                <span className="text-white font-mono">{latestSnapshot?.reconError?.toFixed(6) || selectedUser.reconError?.toFixed(6) || 'N/A'}</span>
                                            </div>
                                            <div>
                                                <span className="text-slate-500 block text-xs">P95 Threshold</span>
                                                <span className="text-white font-mono">{latestSnapshot?.p95Threshold?.toFixed(6) || selectedUser.p95Threshold?.toFixed(6) || 'N/A'}</span>
                                            </div>
                                            <div>
                                                <span className="text-slate-500 block text-xs">Training Mean</span>
                                                <span className="text-white font-mono">{latestSnapshot?.trainMean?.toFixed(6) || selectedUser.trainMean?.toFixed(6) || 'N/A'}</span>
                                            </div>
                                            <div>
                                                <span className="text-slate-500 block text-xs">Training Std Dev</span>
                                                <span className="text-white font-mono">{latestSnapshot?.trainStd?.toFixed(6) || selectedUser.trainStd?.toFixed(6) || 'N/A'}</span>
                                            </div>
                                            <div className="col-span-2 pt-2 border-t border-white/5 mt-2">
                                                <span className="text-slate-500 block text-xs mb-1">Last Analysis Event</span>
                                                <span className="text-indigo-300 font-mono text-xs break-all bg-indigo-500/10 px-2 py-1 rounded">
                                                    {latestSnapshot?.metadata?.eventId || latestSnapshot?.eventType || selectedUser.metadata?.eventId || selectedUser.eventType || 'Unknown Event'}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default SecurityTab;