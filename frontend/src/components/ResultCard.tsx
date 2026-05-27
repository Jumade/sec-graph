"use client";
import { useState } from "react";
import type { Citation } from "@/lib/api";

interface Props {
  answer: string;
  citations: Citation[];
  graphContext: string;
  entities: string[];
}

export default function ResultCard({ answer, citations, graphContext, entities }: Props) {
  const [showCitations, setShowCitations] = useState(false);
  const [showGraph, setShowGraph] = useState(false);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 space-y-4">
      <p className="text-gray-100 leading-relaxed whitespace-pre-wrap">{answer}</p>

      {entities.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {entities.map((e) => (
            <span key={e} className="text-xs bg-emerald-900/50 text-emerald-300 px-2 py-0.5 rounded-full border border-emerald-800">
              {e}
            </span>
          ))}
        </div>
      )}

      {graphContext && (
        <div>
          <button
            onClick={() => setShowGraph(!showGraph)}
            className="text-xs text-gray-500 hover:text-gray-300 underline"
          >
            {showGraph ? "Hide" : "Show"} graph context
          </button>
          {showGraph && (
            <pre className="mt-2 text-xs text-gray-400 bg-gray-950 p-3 rounded overflow-auto max-h-40">
              {graphContext}
            </pre>
          )}
        </div>
      )}

      {citations.length > 0 && (
        <div>
          <button
            onClick={() => setShowCitations(!showCitations)}
            className="text-xs text-gray-500 hover:text-gray-300 underline"
          >
            {showCitations ? "Hide" : "Show"} {citations.length} source{citations.length > 1 ? "s" : ""}
          </button>
          {showCitations && (
            <ul className="mt-2 space-y-1">
              {citations.map((c, i) => (
                <li key={i} className="text-xs text-gray-500">
                  <code className="text-gray-400">{c.filing_id}</code>
                  {" "}· {c.ticker} {c.form_type} {c.filed_date}
                  {c.score != null && <span className="ml-1 text-gray-600">(score: {c.score.toFixed(3)})</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
