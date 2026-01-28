"use client";

import Link from "next/link";
import { useRouter, useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  PieChart,
  Pie,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { toast } from "sonner";

const COLORS = ["#0088FE", "#00C49F", "#FFBB28", "#FF8042"];

function isTerminalStatus(status) {
  if (!status) return false;
  const s = status.toLowerCase();
  return s === "done" || s === "success" || s === "failed" || s === "error";
}

export default function ProjectPage() {
  const router = useRouter();
  const params = useParams();
  const rawName = params?.name;
  const name = Array.isArray(rawName) ? rawName[0] : rawName;

  const [projectMeta, setProjectMeta] = useState(null);
  const [ops, setOps] = useState([]);
  const [bundles, setBundles] = useState([]);
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [opFilter, setOpFilter] = useState("");
  const [jobStarting, setJobStarting] = useState(false);
  const [benchmark, setBenchmark] = useState(null);

  const refreshAll = async () => {
    if (!name) return;
    setLoading(true);
    try {
      const [projRes, opsRes, bundlesRes, benchRes] = await Promise.all([
        fetch(`/api/projects/${name}`),
        fetch(`/api/projects/${name}/ops`),
        fetch(`/api/projects/${name}/bundles`),
        fetch(`/api/projects/${name}/benchmark`),
      ]);

      if (projRes.ok) {
        const data = await projRes.json();
        setProjectMeta(data.project || null);
      }
      if (opsRes.ok) {
        const data = await opsRes.json();
        setOps(data.ops || []);
      }
      if (bundlesRes.ok) {
        const data = await bundlesRes.json();
        setBundles(data.bundles || []);
      }
      if (benchRes.ok || benchRes.status === 404) {
        const data = await benchRes.json();
        setBenchmark(data.benchmark || null);
      }
    } catch (error) {
      console.error(error);
      toast.error("Failed to load project data");
    } finally {
      setLoading(false);
    }
  };

  const refreshJob = async () => {
    if (!name || !job?.job_id) return;
    try {
      const res = await fetch(`/api/projects/${name}/jobs/${job.job_id}`);
      if (res.ok) {
        const data = await res.json();
        const nextJob = data.job || null;
        setJob(nextJob);
        if (nextJob && isTerminalStatus(nextJob.status)) {
          refreshAll();
        }
      }
    } catch (error) {
      console.error(error);
    }
  };

  const startJob = async (jobType) => {
    if (!name) return;
    setJobStarting(true);
    try {
      const res = await fetch(`/api/projects/${name}/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_type: jobType }),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(data.error || "Failed to start job");
        return;
      }
      setJob(data.job);
      toast.success(`Started ${jobType}`);
    } catch (error) {
      console.error(error);
      toast.error("Failed to start job");
    } finally {
      setJobStarting(false);
    }
  };

  useEffect(() => {
    if (!name) return;
    fetch(`/api/projects/${name}`, { method: "PATCH" }).catch(console.error);
    refreshAll();

    const handleKeyDown = (event) => {
      if (event.key === "Escape") router.push("/");
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [name, router]);

  useEffect(() => {
    if (!job?.job_id) return;
    const interval = setInterval(() => {
      refreshJob();
    }, 3000);
    return () => clearInterval(interval);
  }, [job?.job_id]);

  const opsSorted = useMemo(() => {
    return [...ops].sort((a, b) => (b.count || 0) - (a.count || 0));
  }, [ops]);

  const filteredOps = useMemo(() => {
    if (!opFilter) return opsSorted;
    const term = opFilter.toLowerCase();
    return opsSorted.filter((op) =>
      (op.function_name || op.op_id || "").toLowerCase().includes(term)
    );
  }, [opsSorted, opFilter]);

  const pieData = useMemo(() => {
    return opsSorted.slice(0, 4).map((op, idx) => ({
      name: op.function_name || op.op_id || "op",
      value: op.count || 0,
      fill: COLORS[idx % COLORS.length],
    }));
  }, [opsSorted]);

  const operatorFreqData = useMemo(() => {
    return opsSorted.slice(0, 12).map((op) => ({
      operator: op.function_name || op.op_id || "op",
      freq: op.count || 0,
    }));
  }, [opsSorted]);

  const totalOps = ops.length;
  const generatedOps = ops.filter((op) => op.generated).length;
  const optimizedOps = ops.filter((op) => op.optimized).length;

  const barData = [
    { name: "Profiled", time: totalOps, fill: "#22c55e" },
    { name: "Generated", time: generatedOps, fill: "#f97316" },
    { name: "Optimized", time: optimizedOps, fill: "#3b82f6" },
  ];

  const timingData = [
    { ver: "Profiled", time: `${totalOps} ops` },
    { ver: "Generated", time: `${generatedOps} ops` },
    { ver: "Optimized", time: `${optimizedOps} ops` },
  ];

  const hasBenchmark = Boolean(benchmark?.baseline?.count);
  const bundleOk = benchmark?.bundle_status === "ok";
  const baselineStats = benchmark?.baseline || {};
  const bundleStats = bundleOk ? benchmark?.bundle || {} : {};
  const benchmarkChartData = [
    {
      name: "Baseline",
      mean_ms: baselineStats.mean_ms || 0,
      p95_ms: baselineStats.p95_ms || 0,
    },
    {
      name: "Bundle",
      mean_ms: bundleOk ? bundleStats.mean_ms || 0 : 0,
      p95_ms: bundleOk ? bundleStats.p95_ms || 0 : 0,
    },
  ];
  const fmtMs = (val) => (Number.isFinite(val) ? val.toFixed(3) : "-");

  return (
    <div className="flex min-h-screen bg-zinc-950 text-zinc-100 font-sans">
      <div className="absolute top-2 right-6">
        <Link
          href="/settings"
          className="flex items-center justify-center p-2 rounded-full hover:bg-zinc-800 transition-colors text-zinc-400 hover:text-white"
          aria-label="Settings"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.1a2 2 0 0 1-1-1.74v-.51a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        </Link>
      </div>
      <div className="absolute top-2 right-16 z-10">
        <Link
          href="/"
          className="flex items-center justify-center p-2 rounded-full hover:bg-zinc-800 transition-colors text-zinc-400 hover:text-white bg-zinc-950/50 backdrop-blur-sm"
          aria-label="Go Back"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y1="9" x2="9" y2="15"></line>
            <line x1="9" y1="9" x2="15" y2="15"></line>
          </svg>
        </Link>
      </div>
      {/* Sidebar */}
      <aside className="w-1/4 border-r border-zinc-900 flex flex-col p-4 space-y-6">
        <div>
          <h2 className="text-xl font-bold mb-4 text-zinc-100">Operators:</h2>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Search..."
              value={opFilter}
              onChange={(e) => setOpFilter(e.target.value)}
              className="flex-1 bg-zinc-900 border border-zinc-800 rounded px-3 py-2 text-sm focus:outline-none focus:border-zinc-700 transition-colors"
            />
            <button
              className="bg-zinc-800 hover:bg-zinc-700 px-4 py-2 rounded text-sm font-medium transition-colors"
              onClick={() => setOpFilter("")}
            >
              Clear
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto space-y-2 pr-2 custom-scrollbar">
          {filteredOps.length > 0 ? (
            filteredOps.map((op) => (
              <button
                key={op.op_id}
                className="w-full text-left bg-zinc-900/50 hover:bg-zinc-800 border border-zinc-800/50 rounded px-4 py-3 text-sm font-mono text-zinc-300 transition-all"
              >
                {op.function_name || op.op_id}
              </button>
            ))
          ) : (
            <div className="text-xs text-zinc-500">No ops yet.</div>
          )}
        </div>

        <div className="space-y-4 pt-4 border-t border-zinc-900">
          <button
            className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 rounded shadow-lg shadow-emerald-900/20 transition-all disabled:opacity-50"
            onClick={() => startJob("profile")}
            disabled={jobStarting}
          >
            Profile
          </button>
          <button
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded shadow-lg shadow-blue-900/20 transition-all disabled:opacity-50"
            onClick={() => startJob("generate")}
            disabled={jobStarting}
          >
            Generate
          </button>
          <button
            className="w-full bg-amber-600 hover:bg-amber-500 text-white font-bold py-3 rounded shadow-lg shadow-amber-900/20 transition-all disabled:opacity-50"
            onClick={() => startJob("optimize")}
            disabled={jobStarting}
          >
            Optimize
          </button>
          <button
            className="w-full bg-zinc-100 hover:bg-white text-zinc-950 font-bold py-3 rounded shadow-lg shadow-zinc-500/20 transition-all disabled:opacity-50"
            onClick={() => startJob("export")}
            disabled={jobStarting}
          >
            Export
          </button>
          <button
            className="w-full bg-purple-600 hover:bg-purple-500 text-white font-bold py-3 rounded shadow-lg shadow-purple-900/20 transition-all disabled:opacity-50"
            onClick={() => startJob("benchmark")}
            disabled={jobStarting}
          >
            Benchmark
          </button>
          <button
            className="w-full bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-bold py-3 rounded transition-all disabled:opacity-50"
            onClick={() => startJob("smoke")}
            disabled={jobStarting}
          >
            Smoke Test
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="w-3/4 p-8 overflow-y-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-3xl font-bold tracking-tight">Project: {name}</h1>
          <div className="flex gap-3">
            <button
              className="bg-zinc-800 hover:bg-zinc-700 px-4 py-2 rounded text-sm font-medium transition-colors"
              onClick={refreshAll}
              disabled={loading}
            >
              Refresh
            </button>
            {job?.job_id && (
              <button
                className="bg-zinc-800 hover:bg-zinc-700 px-4 py-2 rounded text-sm font-medium transition-colors"
                onClick={refreshJob}
              >
                Refresh Job
              </button>
            )}
          </div>
        </div>

        {projectMeta && (
          <div className="mb-8 grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-4">
              <div className="text-xs text-zinc-500 uppercase">Mode</div>
              <div className="text-lg font-semibold">Mode {projectMeta.mode}</div>
            </div>
            <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-4">
              <div className="text-xs text-zinc-500 uppercase">Profiled</div>
              <div className="text-lg font-semibold">{projectMeta.profiler_ops}</div>
            </div>
            <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-4">
              <div className="text-xs text-zinc-500 uppercase">Generated</div>
              <div className="text-lg font-semibold">{projectMeta.generated_ops}</div>
            </div>
            <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg p-4">
              <div className="text-xs text-zinc-500 uppercase">Optimized</div>
              <div className="text-lg font-semibold">{projectMeta.optimized_ops}</div>
            </div>
          </div>
        )}

        {job?.job_id && (
          <div className="mb-8 bg-zinc-900/40 border border-zinc-800 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-zinc-400">Job</div>
                <div className="text-lg font-semibold">
                  {job.job_type} - {job.status}
                </div>
              </div>
              <div className="text-xs text-zinc-500">id: {job.job_id}</div>
            </div>
            <pre className="mt-3 text-xs bg-zinc-950/40 border border-zinc-800 rounded p-3 max-h-64 overflow-auto whitespace-pre-wrap">
              {job.log_tail || ""}
            </pre>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
          <div className="space-y-6">
            <h3 className="text-xl font-semibold border-b border-zinc-800 pb-2">
              Operator Info
            </h3>
            <div className="h-64 bg-zinc-900/30 rounded-xl border border-zinc-800 p-4 flex flex-col items-center">
              <h4 className="text-sm font-medium text-zinc-400 mb-2">
                Operator Usage (Top 4)
              </h4>
              {pieData.length === 0 ? (
                <div className="text-xs text-zinc-500 mt-8">No ops yet.</div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      innerRadius={60}
                      outerRadius={80}
                      paddingAngle={5}
                      dataKey="value"
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#18181b",
                        borderColor: "#27272a",
                        borderRadius: "8px",
                      }}
                      itemStyle={{ color: "#e4e4e7" }}
                    />
                    <Legend
                      layout="vertical"
                      verticalAlign="middle"
                      align="right"
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="overflow-hidden rounded-xl border border-zinc-800">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-900 text-zinc-400 font-medium uppercase text-xs">
                  <tr>
                    <th className="px-6 py-3">Operator</th>
                    <th className="px-6 py-3">Count</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800 bg-zinc-900/50">
                  {operatorFreqData.length > 0 ? (
                    operatorFreqData.map((row, i) => (
                      <tr key={i} className="hover:bg-zinc-800/50 transition-colors">
                        <td className="px-6 py-3 font-mono text-zinc-300">
                          {row.operator}
                        </td>
                        <td className="px-6 py-3 text-zinc-300">{row.freq}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td className="px-6 py-3 text-zinc-500" colSpan={2}>
                        No ops yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="space-y-6">
            <h3 className="text-xl font-semibold border-b border-zinc-800 pb-2">
              Pipeline Status
            </h3>
            <div className="h-64 bg-zinc-900/30 rounded-xl border border-zinc-800 p-4 flex flex-col items-center">
              <h4 className="text-sm font-medium text-zinc-400 mb-2">
                Ops per Stage
              </h4>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                  <XAxis dataKey="name" stroke="#71717a" tick={{ fill: "#71717a", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis stroke="#71717a" tick={{ fill: "#71717a", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    cursor={{ fill: "#27272a" }}
                    contentStyle={{
                      backgroundColor: "#18181b",
                      borderColor: "#27272a",
                      borderRadius: "8px",
                    }}
                    itemStyle={{ color: "#e4e4e7" }}
                  />
                  <Bar dataKey="time" />
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="overflow-hidden rounded-xl border border-zinc-800">
              <table className="w-full text-sm text-left">
                <thead className="bg-zinc-900 text-zinc-400 font-medium uppercase text-xs">
                  <tr>
                    <th className="px-6 py-3">Stage</th>
                    <th className="px-6 py-3">Count</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800 bg-zinc-900/50">
                  {timingData.map((row, i) => (
                    <tr key={i} className="hover:bg-zinc-800/50 transition-colors">
                      <td className="px-6 py-3 text-zinc-300">{row.ver}</td>
                      <td className="px-6 py-3 text-zinc-300">{row.time}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="mb-12 space-y-4">
          <h3 className="text-xl font-semibold border-b border-zinc-800 pb-2">
            Benchmark
          </h3>
          {!hasBenchmark ? (
            <div className="text-sm text-zinc-500">
              Run Benchmark to see results. If no bundle exists, it will show
              baseline-only timings.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="h-64 bg-zinc-900/30 rounded-xl border border-zinc-800 p-4 flex flex-col items-center">
                <h4 className="text-sm font-medium text-zinc-400 mb-2">
                  Mean vs P95 (ms)
                </h4>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={benchmarkChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                    <XAxis dataKey="name" stroke="#71717a" tick={{ fill: "#71717a", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis stroke="#71717a" tick={{ fill: "#71717a", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      cursor={{ fill: "#27272a" }}
                      contentStyle={{
                        backgroundColor: "#18181b",
                        borderColor: "#27272a",
                        borderRadius: "8px",
                      }}
                      itemStyle={{ color: "#e4e4e7" }}
                    />
                    <Legend />
                    <Bar dataKey="mean_ms" name="mean_ms" fill="#22c55e" />
                    <Bar dataKey="p95_ms" name="p95_ms" fill="#3b82f6" />
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="overflow-hidden rounded-xl border border-zinc-800">
                <table className="w-full text-sm text-left">
                  <thead className="bg-zinc-900 text-zinc-400 font-medium uppercase text-xs">
                    <tr>
                      <th className="px-6 py-3">Variant</th>
                      <th className="px-6 py-3">Mean</th>
                      <th className="px-6 py-3">Median</th>
                      <th className="px-6 py-3">P95</th>
                      <th className="px-6 py-3">Min</th>
                      <th className="px-6 py-3">Max</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800 bg-zinc-900/50">
                    <tr className="hover:bg-zinc-800/50 transition-colors">
                      <td className="px-6 py-3 text-zinc-300">Baseline</td>
                      <td className="px-6 py-3 text-zinc-300">{fmtMs(baselineStats.mean_ms)}</td>
                      <td className="px-6 py-3 text-zinc-300">{fmtMs(baselineStats.median_ms)}</td>
                      <td className="px-6 py-3 text-zinc-300">{fmtMs(baselineStats.p95_ms)}</td>
                      <td className="px-6 py-3 text-zinc-300">{fmtMs(baselineStats.min_ms)}</td>
                      <td className="px-6 py-3 text-zinc-300">{fmtMs(baselineStats.max_ms)}</td>
                    </tr>
                    <tr className="hover:bg-zinc-800/50 transition-colors">
                      <td className="px-6 py-3 text-zinc-300">Bundle</td>
                      <td className="px-6 py-3 text-zinc-300">
                        {bundleOk ? fmtMs(bundleStats.mean_ms) : "missing"}
                      </td>
                      <td className="px-6 py-3 text-zinc-300">
                        {bundleOk ? fmtMs(bundleStats.median_ms) : "missing"}
                      </td>
                      <td className="px-6 py-3 text-zinc-300">
                        {bundleOk ? fmtMs(bundleStats.p95_ms) : "missing"}
                      </td>
                      <td className="px-6 py-3 text-zinc-300">
                        {bundleOk ? fmtMs(bundleStats.min_ms) : "missing"}
                      </td>
                      <td className="px-6 py-3 text-zinc-300">
                        {bundleOk ? fmtMs(bundleStats.max_ms) : "missing"}
                      </td>
                    </tr>
                  </tbody>
                </table>
                <div className="px-6 py-3 text-xs text-zinc-500 border-t border-zinc-800 bg-zinc-950/40">
                  Speedup: {Number.isFinite(benchmark?.speedup) ? benchmark.speedup.toFixed(3) + "x" : "n/a"}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="bg-zinc-900/30 border border-zinc-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-zinc-200">Bundles</h3>
            <span className="text-xs text-zinc-500">
              {bundles.length} total
            </span>
          </div>
          {bundles.length === 0 ? (
            <div className="text-xs text-zinc-500">No bundles yet. Run Export.</div>
          ) : (
            <div className="space-y-2">
              {bundles.map((b) => (
                <div key={b.name} className="bg-zinc-950/40 border border-zinc-800 rounded-lg p-3">
                  <div className="text-sm font-medium">{b.name}</div>
                  <div className="text-xs text-zinc-500 break-all">{b.path}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
