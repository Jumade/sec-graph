"use client";
import { useState } from "react";
import { queryGraph, getEntitySubgraph, QueryResponse } from "@/lib/api";
import ResultCard from "@/components/ResultCard";
import GraphViewer from "@/components/GraphViewer";

const EXAMPLE_QUERIES = [
  "Which suppliers are indirectly dependent on NVIDIA?",
  "Which companies mention supply-chain risk related to TSMC?",
  "Show relationships between OpenAI, Microsoft, and GPU vendors.",
  "Which cybersecurity firms are repeatedly associated with ransomware incidents?",
];

export default function QueryPage() {
  const [question, setQuestion] = useState("");
  const [companyFilter, setCompanyFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [error, setError] = useState("");
  const [graphData, setGraphData] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const res = await queryGraph(question.trim(), companyFilter.trim() || undefined);
      setResult(res);
      setGraphData(res.graph_subgraph);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Query failed");
    } finally {
      setLoading(false);
    }
  };

  const handleNodeClick = async (name: string) => {
    try {
      const sub = await getEntitySubgraph(name, 2);
      setGraphData(sub);
    } catch {}
  };

  return (
    <main className="max-w-7xl mx-auto p-8 space-y-5">
      <h1 className="text-2xl font-bold">Query the Graph</h1>

      <div className="flex flex-wrap gap-2">
        {EXAMPLE_QUERIES.map((q) => (
          <button
            key={q}
            onClick={() => setQuestion(q)}
            className="text-xs bg-gray-900 border border-gray-700 hover:border-emerald-600 text-gray-400 hover:text-white px-3 py-1.5 rounded-full transition"
          >
            {q}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a financial intelligence question..."
          className="flex-1 bg-gray-900 border border-gray-700 rounded px-4 py-2.5 focus:outline-none focus:border-emerald-500"
        />
        <input
          value={companyFilter}
          onChange={(e) => setCompanyFilter(e.target.value)}
          placeholder="Filter by ticker (optional)"
          className="w-44 bg-gray-900 border border-gray-700 rounded px-3 py-2.5 focus:outline-none focus:border-emerald-500 text-sm"
        />
        <button
          type="submit"
          disabled={loading}
          className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 px-5 py-2.5 rounded font-medium transition"
        >
          {loading ? "Thinking..." : "Ask"}
        </button>
      </form>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {result && (
        <ResultCard
          answer={result.answer}
          citations={result.citations}
          graphContext={result.graph_context}
          entities={result.entities}
        />
      )}
      {!result && !loading && (
        <p className="text-gray-600 text-sm">Ask a question to see the answer here.</p>
      )}

      <div className="bg-gray-950 border border-gray-800 rounded-xl overflow-hidden" style={{ height: 560 }}>
        <GraphViewer
          nodes={graphData.nodes}
          edges={graphData.edges}
          onNodeClick={handleNodeClick}
        />
      </div>
    </main>
  );
}
