"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { Check, CircleHelp, X } from "lucide-react";

export function Brand({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand ${small ? "brand-small" : ""}`}>
      <svg viewBox="0 0 40 40" aria-hidden="true">
        <path
          d="M7 7h12c12 0 19 6 19 14S31 35 19 35H7V7Zm9 8v12h4c6 0 10-2 10-6s-4-6-10-6h-4Z"
          fill="currentColor"
        />
        <circle cx="7" cy="34" r="4" fill="#9caf70" />
      </svg>
      {!small && (
        <span>
          diocle<span className="brand-period">.</span>
        </span>
      )}
    </span>
  );
}

export function Badge({
  children,
  tone = "green",
  dot = true,
}: {
  children: ReactNode;
  tone?: string;
  dot?: boolean;
}) {
  return (
    <span className={`badge badge-${tone}`}>
      {dot && <span className="status-dot" />}
      {children}
    </span>
  );
}

export function Progress({
  value,
  tone = "green",
}: {
  value: number;
  tone?: string;
}) {
  return (
    <div
      className={`progress progress-${tone}`}
      role="progressbar"
      aria-label="Migration progress"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <span style={{ width: `${value}%` }} />
    </div>
  );
}

export function Modal({
  title,
  subtitle,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    element?.querySelector<HTMLInputElement>("input:not([disabled])")?.focus();
    return () => element?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className={`modal ${wide ? "modal-wide" : ""}`}
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          const box = event.currentTarget.getBoundingClientRect();
          if (
            event.clientX < box.left ||
            event.clientX > box.right ||
            event.clientY < box.top ||
            event.clientY > box.bottom
          )
            onClose();
        }
      }}
      aria-labelledby="modal-title"
    >
      <div className="modal-header">
        <div>
          <h2 id="modal-title">{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close dialog"
        >
          <X size={20} />
        </button>
      </div>
      {children}
    </dialog>
  );
}

export function DemoNote({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`demo-note ${compact ? "compact" : ""}`}>
      <CircleHelp size={15} />
      <span>
        {compact
          ? "Illustrative data · Frontend preview"
          : "You’re exploring a frontend preview. All programs, findings, and test results are synthetic."}
      </span>
    </div>
  );
}

export function Pipeline({ active = 3 }: { active?: number }) {
  return (
    <div className="pipeline">
      {["Upload", "Analyze", "Convert", "Verify", "Report"].map((step, i) => (
        <div
          className={`pipeline-step ${i < active ? "done" : ""} ${i === active ? "current" : ""}`}
          key={step}
        >
          <span className="pipeline-circle">
            {i < active ? <Check size={12} /> : i + 1}
          </span>
          <span>{step}</span>
        </div>
      ))}
    </div>
  );
}
