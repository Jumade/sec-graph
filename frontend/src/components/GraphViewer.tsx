"use client";
import dynamic from "next/dynamic";
import { useMemo, useRef, useState, useEffect } from "react";
import type { GraphNode, GraphEdge } from "@/lib/api";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const LABEL_COLORS: Record<string, string> = {
  Company: "#34d399",
  Person: "#60a5fa",
  Product: "#f59e0b",
  Risk: "#f87171",
  Industry: "#a78bfa",
  Location: "#fb923c",
  Regulation: "#e879f9",
  default: "#9ca3af",
};

const LEGEND = Object.entries(LABEL_COLORS).filter(([k]) => k !== "default");

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (name: string) => void;
}

export default function GraphViewer({ nodes, edges, onNodeClick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);
  const [dims, setDims] = useState({ width: 800, height: 500 });

  useEffect(() => {
    if (!containerRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setDims({ width: Math.floor(width), height: Math.floor(height) });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  const MAX_DISPLAY = 60;

  const { graphData, totalNodes } = useMemo(() => {
    // Prune oversized graphs: keep the top MAX_DISPLAY nodes by connection degree
    const degree: Record<string, number> = {};
    edges.forEach((e) => {
      degree[e.source] = (degree[e.source] || 0) + 1;
      degree[e.target] = (degree[e.target] || 0) + 1;
    });

    const sorted = [...nodes].sort(
      (a, b) => (degree[b.name] || 0) - (degree[a.name] || 0)
    );
    const display = sorted.slice(0, MAX_DISPLAY);
    const displaySet = new Set(display.map((n) => n.name));

    return {
      totalNodes: nodes.length,
      graphData: {
        nodes: display.map((n) => ({
          ...n,
          id: n.name,
          color: LABEL_COLORS[n.label] || LABEL_COLORS.default,
        })),
        links: edges
          .filter((e) => displaySet.has(e.source) && displaySet.has(e.target))
          .map((e) => ({ source: e.source, target: e.target, label: e.type })),
      },
    };
  }, [nodes, edges]);

  // Tune forces whenever graph data changes so labels have room to breathe
  useEffect(() => {
    const fg = graphRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-800);
    fg.d3Force("link")?.distance(180).strength(0.3);
    fg.d3ReheatSimulation();
  }, [graphData]);

  if (nodes.length === 0) {
    return (
      <div ref={containerRef} className="flex flex-col items-center justify-center h-full gap-2 text-gray-600 text-sm">
        <svg className="w-10 h-10 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <circle cx="6" cy="6" r="2" /><circle cx="18" cy="6" r="2" /><circle cx="12" cy="18" r="2" />
          <line x1="8" y1="6" x2="16" y2="6" /><line x1="6" y1="8" x2="11" y2="16" /><line x1="18" y1="8" x2="13" y2="16" />
        </svg>
        <span>Ask a question to populate the graph</span>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative w-full h-full">
      <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        width={dims.width}
        height={dims.height}
        backgroundColor="#030712"
        nodeLabel={() => ""}
        linkColor={() => "#374151"}
        linkWidth={1.5}
        linkDirectionalArrowLength={6}
        linkDirectionalArrowRelPos={1}
        linkDirectionalParticles={1}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleColor={() => "#4b5563"}
        cooldownTicks={80}
        onEngineStop={() => graphRef.current?.zoomToFit(250, 48)}
        onNodeClick={(n: any) => onNodeClick?.(n.name)}
        nodeCanvasObject={(node: any, ctx, globalScale) => {
          const r = 7;

          // glow ring
          ctx.shadowColor = node.color;
          ctx.shadowBlur = 12;
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
          ctx.strokeStyle = node.color;
          ctx.lineWidth = 2;
          ctx.stroke();
          ctx.shadowBlur = 0;

          // inner fill
          ctx.beginPath();
          ctx.arc(node.x, node.y, r - 1, 0, 2 * Math.PI);
          ctx.fillStyle = node.color + "30";
          ctx.fill();

          // label
          const raw = node.name as string;
          const label = raw.length > 22 ? raw.slice(0, 20) + "…" : raw;
          const fontSize = Math.max(10, Math.min(13, 13 / globalScale));
          ctx.font = `500 ${fontSize}px system-ui, sans-serif`;
          const tw = ctx.measureText(label).width;
          const pad = 4;
          const lx = node.x - tw / 2;
          const ly = node.y + r + 5;

          // pill background
          ctx.fillStyle = "rgba(3, 7, 18, 0.88)";
          ctx.beginPath();
          const rx = lx - pad, ry = ly - 1, rw = tw + pad * 2, rh = fontSize + 4, rad = 3;
          ctx.moveTo(rx + rad, ry);
          ctx.lineTo(rx + rw - rad, ry);
          ctx.arcTo(rx + rw, ry, rx + rw, ry + rh, rad);
          ctx.lineTo(rx + rw, ry + rh - rad);
          ctx.arcTo(rx + rw, ry + rh, rx, ry + rh, rad);
          ctx.lineTo(rx + rad, ry + rh);
          ctx.arcTo(rx, ry + rh, rx, ry, rad);
          ctx.lineTo(rx, ry + rad);
          ctx.arcTo(rx, ry, rx + rw, ry, rad);
          ctx.closePath();
          ctx.fill();

          // label text
          ctx.fillStyle = "#f3f4f6";
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillText(label, node.x, ly);
          ctx.textBaseline = "alphabetic";
        }}
        linkCanvasObjectMode={() => "after"}
        linkCanvasObject={(link: any, ctx, globalScale) => {
          if (globalScale < 0.8) return;
          const s = link.source, t = link.target;
          if (!s || !t || typeof s !== "object" || typeof t !== "object") return;
          const label = (link.label as string)?.replace(/_/g, " ");
          if (!label) return;
          const mx = (s.x + t.x) / 2;
          const my = (s.y + t.y) / 2;
          const fontSize = Math.max(8, Math.min(10, 10 / globalScale));
          ctx.font = `${fontSize}px system-ui, sans-serif`;
          const tw = ctx.measureText(label).width;
          ctx.fillStyle = "rgba(3,7,18,0.75)";
          ctx.fillRect(mx - tw / 2 - 3, my - fontSize / 2 - 2, tw + 6, fontSize + 4);
          ctx.fillStyle = "#6b7280";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(label, mx, my);
          ctx.textBaseline = "alphabetic";
        }}
      />
      {/* legend */}
      <div className="absolute bottom-3 left-3 flex flex-wrap gap-x-3 gap-y-1">
        {LEGEND.map(([label, color]) => (
          <span key={label} className="flex items-center gap-1 text-xs text-gray-500">
            <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            {label}
          </span>
        ))}
      </div>
      {totalNodes > MAX_DISPLAY && (
        <div className="absolute top-3 right-3 text-xs bg-gray-900/80 border border-gray-700 text-gray-400 px-2 py-1 rounded">
          Showing {MAX_DISPLAY} of {totalNodes} nodes · top by connections
        </div>
      )}
    </div>
  );
}
