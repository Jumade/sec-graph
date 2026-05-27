"use client";
import { useState, useEffect, useRef } from "react";
import { ingestFiling, getStatus, cancelJob, StatusResponse } from "@/lib/api";

const YEARS = Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - i);
const STORAGE_KEY = "sec_graph_jobs";

interface StoredJob {
  job_id: string;
  ticker: string;
  form_type: string;
  years: number[];
  filings_queued: number;
  submitted_at: string;
  stage: string;
  detail: string;
  use_batch: boolean;
}

function loadJobs(): StoredJob[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveJobs(jobs: StoredJob[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(jobs));
}

const TERMINAL_STAGES = ["complete", "error", "stale", "cancelled"];

function StageBadge({ stage }: { stage: string }) {
  const color =
    stage === "complete"
      ? "bg-emerald-900 text-emerald-300"
      : stage === "error"
      ? "bg-red-900 text-red-300"
      : stage === "stale"
      ? "bg-gray-700 text-gray-400"
      : stage === "cancelled"
      ? "bg-zinc-800 text-zinc-400"
      : stage === "waiting_for_batch"
      ? "bg-blue-900 text-blue-300"
      : "bg-yellow-900 text-yellow-300";
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${color}`}>
      {stage || "queued"}
    </span>
  );
}

export default function IngestPage() {
  const [ticker, setTicker] = useState("");
  const [formType, setFormType] = useState<"10-K" | "10-Q" | "8-K">("10-K");
  const [years, setYears] = useState<number[]>([YEARS[0]]);
  const [useBatch, setUseBatch] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<StoredJob[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load jobs from localStorage on mount
  useEffect(() => {
    setJobs(loadJobs());
  }, []);

  // Poll all incomplete jobs every 3 s
  useEffect(() => {
    intervalRef.current = setInterval(async () => {
      const current = loadJobs();
      const incomplete = current.filter((j) => !TERMINAL_STAGES.includes(j.stage));
      if (incomplete.length === 0) return;

      const updated = [...current];
      await Promise.all(
        incomplete.map(async (job) => {
          try {
            const s = await getStatus(job.job_id);
            const idx = updated.findIndex((j) => j.job_id === job.job_id);
            if (idx !== -1) {
              updated[idx] = { ...updated[idx], stage: s.stage, detail: s.detail };
            }
          } catch (err: any) {
            // 404 = Redis key gone (worker died / TTL expired) — stop polling
            if (err?.response?.status === 404) {
              const idx = updated.findIndex((j) => j.job_id === job.job_id);
              if (idx !== -1) {
                const detail = job.use_batch
                  ? "Status key expired — batch may still be running on OpenAI. Retry to re-attach."
                  : "Lost after restart — click Retry";
                updated[idx] = { ...updated[idx], stage: "stale", detail };
              }
            }
          }
        })
      );
      saveJobs(updated);
      setJobs([...updated]);
    }, 3000);

    return () => clearInterval(intervalRef.current!);
  }, []);

  const toggleYear = (y: number) =>
    setYears((prev) =>
      prev.includes(y) ? prev.filter((v) => v !== y) : [...prev, y]
    );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await ingestFiling({
        ticker: ticker.trim().toUpperCase(),
        form_type: formType,
        years,
        use_batch: useBatch,
      });
      const newJob: StoredJob = {
        job_id: res.job_id,
        ticker: ticker.trim().toUpperCase(),
        form_type: formType,
        years,
        filings_queued: res.filings_queued,
        submitted_at: new Date().toISOString(),
        stage: "queued",
        detail: "",
        use_batch: useBatch,
      };
      const updated = [newJob, ...loadJobs()];
      saveJobs(updated);
      setJobs(updated);
      setTicker("");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Ingest failed");
    } finally {
      setLoading(false);
    }
  };

  const clearCompleted = () => {
    const updated = jobs.filter((j) => j.stage !== "complete");
    saveJobs(updated);
    setJobs(updated);
  };

  const handleCancel = async (job: StoredJob) => {
    try {
      await cancelJob(job.job_id);
    } catch {
      // job may already be gone — update locally regardless
    }
    const updated = jobs.map((j) =>
      j.job_id === job.job_id ? { ...j, stage: "cancelled", detail: "Cancelled by user" } : j
    );
    saveJobs(updated);
    setJobs(updated);
  };

  const retryJob = async (job: StoredJob) => {
    try {
      const res = await ingestFiling({
        ticker: job.ticker,
        form_type: job.form_type as "10-K" | "10-Q" | "8-K",
        years: job.years,
        use_batch: job.use_batch,
      });
      const retried: StoredJob = {
        ...job,
        job_id: res.job_id,
        filings_queued: res.filings_queued,
        submitted_at: new Date().toISOString(),
        stage: "queued",
        detail: "",
      };
      const updated = jobs.map((j) => (j.job_id === job.job_id ? retried : j));
      saveJobs(updated);
      setJobs(updated);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Retry failed");
    }
  };

  return (
    <main className="max-w-5xl mx-auto p-8 grid grid-cols-1 lg:grid-cols-2 gap-10">
      {/* Left: form */}
      <div>
        <h1 className="text-2xl font-bold mb-6">Ingest SEC Filings</h1>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Ticker</label>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="NVDA"
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 focus:outline-none focus:border-emerald-500"
              required
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Form Type</label>
            <select
              value={formType}
              onChange={(e) => setFormType(e.target.value as any)}
              className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 focus:outline-none focus:border-emerald-500"
            >
              {["10-K", "10-Q", "8-K"].map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Years</label>
            <div className="flex gap-2 flex-wrap">
              {YEARS.map((y) => (
                <button
                  key={y}
                  type="button"
                  onClick={() => toggleYear(y)}
                  className={`px-3 py-1 rounded text-sm border transition ${
                    years.includes(y)
                      ? "bg-emerald-600 border-emerald-500 text-white"
                      : "bg-gray-900 border-gray-700 text-gray-400 hover:border-gray-500"
                  }`}
                >
                  {y}
                </button>
              ))}
            </div>
          </div>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={useBatch}
              onChange={(e) => setUseBatch(e.target.checked)}
              className="accent-emerald-500 w-4 h-4"
            />
            <span className="text-sm text-gray-400">
              Batch mode{" "}
              <span className="text-gray-600">(50% cheaper, results in up to 24h)</span>
            </span>
          </label>
          <button
            type="submit"
            disabled={loading || years.length === 0}
            className="w-full bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded py-2 font-medium transition"
          >
            {loading ? "Queuing..." : "Start Ingestion"}
          </button>
        </form>
        {error && <p className="mt-4 text-red-400 text-sm">{error}</p>}
      </div>

      {/* Right: job list */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Jobs</h2>
          {jobs.some((j) => j.stage === "complete") && (
            <button
              onClick={clearCompleted}
              className="text-xs text-gray-500 hover:text-gray-300 underline"
            >
              Clear completed
            </button>
          )}
        </div>

        {jobs.length === 0 ? (
          <p className="text-sm text-gray-600">No jobs yet.</p>
        ) : (
          <ul className="space-y-3">
            {jobs.map((job) => (
              <li
                key={job.job_id}
                className="bg-gray-900 border border-gray-800 rounded-lg p-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="font-medium text-white">{job.ticker}</span>
                    <span className="text-gray-500 text-sm ml-2">
                      {job.form_type} · {job.years.join(", ")}
                    </span>
                    <span className="text-gray-600 text-xs ml-2">
                      ({job.filings_queued} filing{job.filings_queued !== 1 ? "s" : ""})
                    </span>
                  </div>
                  <StageBadge stage={job.stage} />
                </div>
                {job.detail && (
                  <p className="text-xs text-gray-500 mt-1.5">{job.detail}</p>
                )}
                <div className="flex items-center justify-between mt-1">
                  <p className="text-xs text-gray-700">
                    {new Date(job.submitted_at).toLocaleString()}
                  </p>
                  <div className="flex gap-3">
                    {!TERMINAL_STAGES.includes(job.stage) && (
                      <button
                        onClick={() => handleCancel(job)}
                        className="text-xs text-gray-500 hover:text-red-400 underline"
                      >
                        Cancel
                      </button>
                    )}
                    {(job.stage === "stale" || job.stage === "error" || job.stage === "cancelled") && (
                      <button
                        onClick={() => retryJob(job)}
                        className="text-xs text-emerald-500 hover:text-emerald-400 underline"
                      >
                        Retry
                      </button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
