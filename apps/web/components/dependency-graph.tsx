"use client";

import { useState } from "react";
import {
  ArrowUpRight,
  FileCode2,
  Focus,
  Minus,
  Plus,
  ShieldAlert,
} from "lucide-react";
import { Badge } from "./ui";

const nodes = [
  {
    id: "ACCT-MAIN",
    x: 330,
    y: 25,
    kind: "Program",
    lines: 1248,
    risky: false,
  },
  {
    id: "PAYMENT-PROC",
    x: 100,
    y: 165,
    kind: "Program",
    lines: 864,
    risky: true,
  },
  {
    id: "BALANCE-CALC",
    x: 550,
    y: 165,
    kind: "Program",
    lines: 532,
    risky: false,
  },
  {
    id: "FRAUD-CHECK",
    x: 100,
    y: 310,
    kind: "Program",
    lines: 716,
    risky: true,
  },
  {
    id: "CUSTOMER",
    x: 330,
    y: 310,
    kind: "Copybook",
    lines: 142,
    risky: false,
  },
  {
    id: "ACCOUNT-REC",
    x: 550,
    y: 310,
    kind: "Copybook",
    lines: 98,
    risky: false,
  },
];
const edges = [
  [0, 1],
  [0, 2],
  [1, 3],
  [1, 4],
  [2, 4],
  [2, 5],
];

export default function DependencyGraph({
  compact = false,
  onExplore,
}: {
  compact?: boolean;
  onExplore?: () => void;
}) {
  const [selected, setSelected] = useState("ACCT-MAIN");
  const [zoom, setZoom] = useState(1);
  const node = nodes.find((n) => n.id === selected)!;
  return (
    <section className={`panel graph-panel ${compact ? "graph-compact" : ""}`}>
      <div className="panel-heading">
        <div>
          <h2>
            See the bigger picture
            <span className="small-tag">Dependency graph</span>
          </h2>
          <p>Understand your system before you change it.</p>
        </div>
        {compact && (
          <button
            className="icon-button"
            aria-label="Explore dependency graph"
            onClick={onExplore}
          >
            <ArrowUpRight size={19} />
          </button>
        )}
      </div>
      <div className="graph-area">
        <svg
          viewBox="0 0 840 405"
          className="graph-svg"
          role="group"
          aria-label="Synthetic COBOL dependency graph. Account Main calls Payment Processing and Balance Calculation."
        >
          <defs>
            <marker
              id={compact ? "arrow-small" : "arrow-large"}
              markerWidth="7"
              markerHeight="7"
              refX="6"
              refY="3.5"
              orient="auto"
            >
              <path d="M0 0L7 3.5L0 7" fill="none" stroke="#a7b9a5" />
            </marker>
          </defs>
          <g
            transform={`translate(${420 * (1 - zoom)} ${200 * (1 - zoom)}) scale(${zoom})`}
          >
            {edges.map(([from, to]) => {
              const a = nodes[from],
                b = nodes[to];
              return (
                <path
                  key={`${from}-${to}`}
                  d={`M ${a.x + 80} ${a.y + 60} C ${a.x + 80} ${a.y + 105}, ${b.x + 80} ${b.y - 45}, ${b.x + 80} ${b.y}`}
                  fill="none"
                  stroke={
                    selected === a.id || selected === b.id
                      ? "#739b78"
                      : "#c9d4c6"
                  }
                  strokeWidth="1.5"
                  strokeDasharray={b.kind === "Copybook" ? "5 4" : undefined}
                  markerEnd={`url(#${compact ? "arrow-small" : "arrow-large"})`}
                />
              );
            })}
            {nodes.map((n) => (
              <g
                key={n.id}
                transform={`translate(${n.x} ${n.y})`}
                className={`graph-node ${selected === n.id ? "selected" : ""}`}
                role="button"
                tabIndex={0}
                aria-label={`Inspect ${n.id}`}
                onClick={() => setSelected(n.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelected(n.id);
                  }
                }}
              >
                <rect width="160" height="60" rx="9" />
                <rect
                  x="12"
                  y="16"
                  width="27"
                  height="28"
                  rx="6"
                  className={
                    n.kind === "Copybook" ? "node-icon copybook" : "node-icon"
                  }
                />
                <text
                  x="25.5"
                  y="35"
                  textAnchor="middle"
                  className="node-symbol"
                >
                  {n.kind === "Copybook" ? "≡" : "‹/›"}
                </text>
                <text x="49" y="28" className="node-name">
                  {n.id}
                </text>
                <text x="49" y="43" className="node-kind">
                  {n.kind}
                </text>
                {n.risky && <circle cx="146" cy="12" r="4" fill="#d89c51" />}
              </g>
            ))}
          </g>
        </svg>
        <div className="graph-legend">
          <span>
            <i />
            Program
          </span>
          <span>
            <i className="legend-copy" />
            Copybook
          </span>
          <span>
            <i className="legend-risk" />
            Risk flagged
          </span>
        </div>
        <div className="graph-controls">
          <button
            className="icon-button"
            aria-label="Zoom out"
            onClick={() => setZoom((z) => Math.max(0.7, z - 0.1))}
          >
            <Minus size={15} />
          </button>
          <button
            className="zoom-value"
            onClick={() => setZoom(1)}
            aria-label="Reset graph zoom"
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            className="icon-button"
            aria-label="Zoom in"
            onClick={() => setZoom((z) => Math.min(1.4, z + 0.1))}
          >
            <Plus size={15} />
          </button>
          <button
            className="icon-button"
            onClick={() => {
              setZoom(1);
              setSelected("ACCT-MAIN");
            }}
            aria-label="Fit graph"
          >
            <Focus size={15} />
          </button>
        </div>
      </div>
      {!compact && (
        <div className="node-details">
          <div className="file-icon">
            <FileCode2 size={22} />
          </div>
          <div>
            <h3>
              {node.id}
              {node.kind === "Copybook" ? ".cpy" : ".cbl"}
            </h3>
            <p>
              {node.kind} · {node.lines.toLocaleString()} lines · Synthetic
              sample
            </p>
          </div>
          <Badge tone={node.risky ? "amber" : "green"}>
            {node.risky ? (
              <>
                <ShieldAlert size={12} /> Review required
              </>
            ) : (
              "No findings"
            )}
          </Badge>
        </div>
      )}
    </section>
  );
}
