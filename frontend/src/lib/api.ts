import axios from "axios";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
});

export interface IngestRequest {
  ticker: string;
  form_type: "10-K" | "10-Q" | "8-K";
  years: number[];
  use_batch?: boolean;
}

export interface IngestResponse {
  job_id: string;
  filings_queued: number;
  message: string;
}

export interface StatusResponse {
  job_id: string;
  stage: string;
  detail: string;
}

export interface Citation {
  filing_id: string | null;
  ticker: string | null;
  filed_date: string | null;
  form_type: string | null;
  score: number | null;
}

export interface GraphNode {
  id: string;
  name: string;
  label: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface QueryResponse {
  answer: string;
  citations: Citation[];
  graph_context: string;
  entities: string[];
  graph_subgraph: { nodes: GraphNode[]; edges: GraphEdge[] };
}

export const ingestFiling = (req: IngestRequest) =>
  api.post<IngestResponse>("/ingest", req).then((r) => r.data);

export const getStatus = (jobId: string) =>
  api.get<StatusResponse>(`/ingest/status/${jobId}`).then((r) => r.data);

export const cancelJob = (jobId: string) =>
  api.delete(`/ingest/${jobId}`).then((r) => r.data);

export const queryGraph = (question: string, companyFilter?: string) =>
  api
    .post<QueryResponse>("/query", { question, company_filter: companyFilter ?? null })
    .then((r) => r.data);

export const getEntitySubgraph = (name: string, depth = 2) =>
  api.get(`/graph/entity/${encodeURIComponent(name)}`, { params: { depth } }).then((r) => r.data);

export const getPath = (from: string, to: string) =>
  api.get("/graph/path", { params: { from, to } }).then((r) => r.data);
