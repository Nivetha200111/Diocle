"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import {
  Activity,
  GitPullRequest,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bell,
  Braces,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  CircleCheck,
  CircleHelp,
  Database,
  Download,
  FileCode2,
  FileText,
  FolderGit2,
  GitBranch,
  Layers3,
  LayoutDashboard,
  ListFilter,
  Menu,
  Network,
  Plus,
  Search,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import {
  activities,
  cobolCode,
  customerCode,
  downloadFile,
  findings,
  initialMigrations,
  javaCode,
  programs,
  reportFor,
  sqlCode,
  testCode,
  type Migration,
  type View,
} from "@/lib/demo";
import { Badge, Brand, DemoNote, Modal, Pipeline, Progress } from "./ui";
import DependencyGraph from "./dependency-graph";
import RunsView from "./runs-view";
import DeliveryView from "./delivery-view";

const nav = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Migrations", icon: FolderGit2 },
  { name: "Dependency graph", icon: Network },
  { name: "Risk findings", icon: ShieldAlert, count: 3 },
  { name: "Conversions", icon: Braces },
  { name: "Verification", icon: ShieldCheck },
  { name: "Reports", icon: FileText },
  { name: "Live runs", icon: Activity },
  { name: "Delivery", icon: GitPullRequest },
] as const;

const descriptions: Record<View, string> = {
  Overview: "A clearer path from legacy code to what’s next.",
  Migrations: "Every modernization journey, in one place.",
  "Dependency graph": "Map the connections. Understand the impact.",
  "Risk findings": "A little attention here makes a big difference.",
  Conversions: "Your business logic, in a modern language.",
  Verification: "Same inputs. Same behavior. Greater confidence.",
  Reports: "The complete story of your modernization.",
  "Live runs": "Real agent runs: what broke, what the agent did, and the proof.",
  Delivery: "A legacy GitHub repository migrated live: analyze, convert, certify, open a pull request, re-verify in CI.",
  Settings: "Make this workspace your own.",
};

function HeroArt() {
  return (
    <div className="hero-art" aria-hidden="true">
      <div className="orbit orbit-one" />
      <div className="orbit orbit-two" />
      <div className="orbit orbit-three" />
      <div className="art-code art-cobol">
        <span className="art-file">
          <FileCode2 size={15} />
          account.cbl
        </span>
        <span className="art-language">COBOL</span>
        <span className="art-line line-long" />
        <span className="art-line" />
        <span className="art-line line-short" />
      </div>
      <div className="art-bridge">
        <Sparkles size={25} />
        <span className="bridge-dot" />
      </div>
      <div className="art-code art-java">
        <span className="art-file">
          <Braces size={15} />
          AccountService.java
        </span>
        <span className="art-language">JAVA</span>
        <span className="art-line line-long" />
        <span className="art-line" />
        <span className="art-line line-short" />
        <span className="art-verified">
          <CircleCheck size={12} />
          Behavior preserved
        </span>
      </div>
      <span className="art-spark spark-one">✧</span>
      <span className="art-spark spark-two">✧</span>
      <span className="art-floating art-db">
        <Database size={19} />
      </span>
      <span className="art-floating art-check">
        <Check size={18} />
      </span>
    </div>
  );
}

function Stats({ openFindings = 3 }: { openFindings?: number }) {
  const items = [
    {
      label: "Programs analyzed",
      value: 44,
      caption: "Across 3 sample migrations",
      icon: FileCode2,
      color: "green",
      note: "+24 this week",
      path: "Migrations",
    },
    {
      label: "Services generated",
      value: "32",
      caption: "From COBOL to modern Java",
      icon: Braces,
      color: "purple",
      note: "72.7% converted",
      path: "Conversions",
    },
    {
      label: "Behavioral match",
      value: "96.8",
      unit: "%",
      caption: "968 of 1,000 test outputs match",
      icon: ShieldCheck,
      color: "green",
      note: "Differential testing",
      path: "Verification",
    },
    {
      label: "Findings to review",
      value: openFindings,
      caption: "Review state saved for this session",
      icon: ShieldAlert,
      color: "orange",
      note: "Needs your attention",
      path: "Risk findings",
    },
  ];
  return (
    <div className="stats-grid">
      {items.map((item) => (
        <div className="stat-card" key={item.label}>
          <div className="stat-top">
            <span>{item.label}</span>
            <span className={`stat-icon ${item.color}`}>
              <item.icon size={18} />
            </span>
          </div>
          <div className="stat-value">
            {item.value}
            <span>{item.unit}</span>
          </div>
          <p>{item.caption}</p>
          <div className={`stat-note ${item.color}`}>
            {item.color === "orange" ? (
              <span className="status-dot" />
            ) : item.path === "Migrations" ? (
              <ArrowUpRight size={12} />
            ) : (
              <span className="status-dot" />
            )}
            {item.note}
          </div>
        </div>
      ))}
    </div>
  );
}

function MigrationList({
  migrations,
  onSelect,
  onNew,
  full = false,
}: {
  migrations: Migration[];
  onSelect: (migration: Migration) => void;
  onNew: () => void;
  full?: boolean;
}) {
  const [filter, setFilter] = useState("All migrations");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("All statuses");
  const visible = migrations.filter(
    (m) =>
      (filter === "All migrations" ||
        (filter === "Active"
          ? m.status !== "Completed"
          : m.status === "Completed")) &&
      (status === "All statuses" || m.status === status) &&
      `${m.name} ${m.id}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <section className="panel migration-panel">
      <div className="panel-heading">
        <div>
          <h2>
            Your migrations <span className="count">{migrations.length}</span>
          </h2>
          <p>Big transformations, one program at a time.</p>
        </div>
        <button className="text-button" onClick={onNew}>
          <Plus size={15} />
          <span>New migration</span>
        </button>
      </div>
      <div className="table-toolbar">
        <div className="tabs" role="tablist" aria-label="Filter migrations">
          {["All migrations", "Active", "Completed"].map((label) => (
            <button
              role="tab"
              aria-selected={filter === label}
              className={filter === label ? "active" : ""}
              key={label}
              onClick={() => setFilter(label)}
            >
              {label}
              {label === "Active" && (
                <span>
                  {migrations.filter((m) => m.status !== "Completed").length}
                </span>
              )}
            </button>
          ))}
        </div>
        <label className="filter-select">
          <ListFilter size={14} />
          <select
            aria-label="Filter migration status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option>All statuses</option>
            <option>In progress</option>
            <option>Completed</option>
            <option>Needs review</option>
          </select>
        </label>
      </div>
      {full && (
        <label className="table-search">
          <Search size={16} />
          <input
            placeholder="Search migrations by name or ID…"
            aria-label="Search migrations"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      )}
      <div className="table-scroll">
        <table className="migration-table">
          <thead>
            <tr>
              <th>Migration</th>
              <th>Status</th>
              <th>Progress</th>
              <th className="updated-col">Last updated</th>
              <th>
                <span className="sr-only">Details</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((m) => (
              <tr key={m.id}>
                <td>
                  <button
                    className="migration-name"
                    onClick={() => onSelect(m)}
                  >
                    <span className={`migration-icon ${m.color}`}>
                      <FolderGit2 size={20} />
                    </span>
                    <span>
                      <strong>{m.name}</strong>
                      <small>
                        {m.programs} programs <span>·</span> {m.copybooks}{" "}
                        copybooks
                      </small>
                    </span>
                  </button>
                </td>
                <td>
                  <Badge
                    tone={
                      m.status === "Needs review"
                        ? "amber"
                        : m.status === "In progress"
                          ? "blue"
                          : "green"
                    }
                  >
                    {m.status}
                  </Badge>
                </td>
                <td>
                  <div className="table-progress">
                    <Progress
                      value={m.progress}
                      tone={m.status === "Needs review" ? "amber" : "green"}
                    />
                    <span>{m.progress}%</span>
                  </div>
                </td>
                <td className="updated-col">{m.updated}</td>
                <td>
                  <button
                    className="icon-button"
                    onClick={() => onSelect(m)}
                    aria-label={`View ${m.name} details`}
                  >
                    <ChevronRight size={17} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {visible.length === 0 && (
          <div className="empty-state">
            <Search size={25} />
            <h3>No migrations found</h3>
            <p>Try a different search or status.</p>
            <button
              className="button secondary"
              onClick={() => {
                setQuery("");
                setStatus("All statuses");
                setFilter("All migrations");
              }}
            >
              Clear filters
            </button>
          </div>
        )}
      </div>
      <div className="table-footer">
        <span>
          Showing {visible.length} of {migrations.length} migrations
        </span>
        <span className="synthetic-label">
          <span className="status-dot" />
          Synthetic sample workspace
        </span>
      </div>
    </section>
  );
}

function ActivityList({
  onView,
  long = false,
}: {
  onView?: () => void;
  long?: boolean;
}) {
  return (
    <section className={`panel activity-panel ${long ? "activity-long" : ""}`}>
      <div className="panel-heading">
        <h2>Recent activity</h2>
        <span className="live-dot" title="Sample activity" />
      </div>
      <div className="activity-list">
        {activities.map((item) => (
          <div className="activity-item" key={item.title}>
            <div className={`activity-icon ${item.kind}`}>
              {item.kind === "review" ? (
                <ShieldAlert size={15} />
              ) : item.kind === "success" ? (
                <CheckCheck size={15} />
              ) : item.kind === "code" ? (
                <Braces size={15} />
              ) : (
                <Network size={15} />
              )}
            </div>
            <div>
              <h3>{item.title}</h3>
              <p>{item.detail}</p>
              <span>{item.time}</span>
            </div>
          </div>
        ))}
      </div>
      {onView && (
        <button className="activity-footer" onClick={onView}>
          View all activity
          <ArrowRight size={14} />
        </button>
      )}
    </section>
  );
}

function CodePreview({
  tab,
  onTab,
  onDownload,
}: {
  tab: string;
  onTab: (tab: string) => void;
  onDownload: () => void;
}) {
  const code =
    tab === "Java service"
      ? javaCode
      : tab === "SQL schema"
        ? sqlCode
        : testCode;
  return (
    <section className="panel conversion-panel">
      <div className="panel-heading">
        <div>
          <h2>A familiar logic. A fresh start.</h2>
          <p>
            Inspect an illustrative conversion from the synthetic payment
            program.
          </p>
        </div>
        <button className="button secondary" onClick={onDownload}>
          <Download size={15} />
          Download example
        </button>
      </div>
      <div className="code-tabs" role="tablist" aria-label="Generated artifact">
        {["Java service", "SQL schema", "Generated tests"].map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={t === tab}
            onClick={() => onTab(t)}
            className={t === tab ? "active" : ""}
          >
            {t === "Java service" ? (
              <Braces size={15} />
            ) : t === "SQL schema" ? (
              <Database size={15} />
            ) : (
              <ShieldCheck size={15} />
            )}
            {t}
          </button>
        ))}
      </div>
      <div className="code-comparison">
        <CodeBlock
          title={tab === "SQL schema" ? "CUSTOMER.cpy" : "PAYMENT-PROC.cbl"}
          label={
            tab === "SQL schema" ? "Original · Copybook" : "Original · COBOL"
          }
          code={tab === "SQL schema" ? customerCode : cobolCode}
        />
        <CodeBlock
          title={
            tab === "Java service"
              ? "PaymentService.java"
              : tab === "SQL schema"
                ? "customers.sql"
                : "PaymentServiceTest.java"
          }
          label="Illustrative output"
          code={code}
          green
        />
      </div>
      <DemoNote compact />
    </section>
  );
}

function CodeBlock({
  title,
  label,
  code,
  green = false,
}: {
  title: string;
  label: string;
  code: string;
  green?: boolean;
}) {
  return (
    <div className={`code-block ${green ? "code-green" : ""}`}>
      <div className="code-heading">
        <span>
          <FileCode2 size={14} />
          {title}
        </span>
        <small>{label}</small>
      </div>
      <pre>
        <code>
          {code.split("\n").map((line, index) => (
            <span
              className={`code-line ${line.trim().startsWith("//") || line.trim().startsWith("--") ? "code-comment" : ""}`}
              key={index}
            >
              <span className="line-number">{index + 1}</span>
              {line || " "}
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}

function VerificationView({ onReport }: { onReport: () => void }) {
  const [filter, setFilter] = useState("All tests");
  const rows = [
    {
      id: "TC-001",
      scenario: "Standard payment",
      original: "97.50",
      converted: "97.50",
      match: true,
    },
    {
      id: "TC-002",
      scenario: "Zero transaction fee",
      original: "100.00",
      converted: "100.00",
      match: true,
    },
    {
      id: "TC-003",
      scenario: "Rounding boundary",
      original: "97.51",
      converted: "97.50",
      match: false,
    },
    {
      id: "TC-004",
      scenario: "Maximum account balance",
      original: "999999999.99",
      converted: "999999999.99",
      match: true,
    },
    {
      id: "TC-005",
      scenario: "Negative balance",
      original: "-12.50",
      converted: "12.50",
      match: false,
    },
  ].filter(
    (row) =>
      filter === "All tests" || (filter === "Matched" ? row.match : !row.match),
  );
  return (
    <>
      <div className="verification-summary panel">
        <div
          className="match-ring"
          style={{ "--match": "96.8%" } as CSSProperties}
        >
          <div>
            <strong>
              96.8<span>%</span>
            </strong>
            <small>behavioral match</small>
          </div>
        </div>
        <div>
          <Badge>Sample verification report</Badge>
          <h2>Trust is built on evidence.</h2>
          <p>
            Run the original COBOL and converted Java on the same inputs.
            <br />
            Compare every output to catch what matters.
          </p>
          <div className="verification-counts">
            <span>
              <i className="green-dot" />
              968 matched
            </span>
            <span>
              <i className="amber-dot" />
              32 mismatched
            </span>
            <span>1,000 total cases</span>
          </div>
        </div>
        <button className="button secondary" onClick={onReport}>
          <Download size={15} />
          Export sample report
        </button>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Output comparison</h2>
            <p>5 illustrative test cases from the core banking sample.</p>
          </div>
          <Badge tone="neutral">GnuCOBOL ↔ Java</Badge>
        </div>
        <div className="table-toolbar">
          <div
            className="tabs"
            role="tablist"
            aria-label="Filter verification cases"
          >
            {["All tests", "Matched", "Mismatched"].map((t) => (
              <button
                key={t}
                role="tab"
                aria-selected={t === filter}
                className={t === filter ? "active" : ""}
                onClick={() => setFilter(t)}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Test case</th>
                <th>Scenario</th>
                <th>COBOL output</th>
                <th>Java output</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td className="mono">{row.id}</td>
                  <td>{row.scenario}</td>
                  <td className="mono">{row.original}</td>
                  <td className={`mono ${!row.match ? "mismatch" : ""}`}>
                    {row.converted}
                  </td>
                  <td>
                    <Badge tone={row.match ? "green" : "amber"}>
                      {row.match ? "Matched" : "Mismatch"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <DemoNote />
      </section>
    </>
  );
}

export default function Workspace() {
  const [view, setView] = useState<View>("Overview");
  const [migrations, setMigrations] = useState<Migration[]>(initialMigrations);
  const [modal, setModal] = useState<
    "new" | "search" | "activity" | "help" | "profile" | null
  >(null);
  const [selected, setSelected] = useState<Migration | null>(null);
  const [notifications, setNotifications] = useState(false);
  const [workspaceMenu, setWorkspaceMenu] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [codeTab, setCodeTab] = useState("Java service");
  const [toast, setToast] = useState("");
  const [search, setSearch] = useState("");
  const [resolved, setResolved] = useState<string[]>([]);
  const [expandedFinding, setExpandedFinding] = useState<string | null>(
    "RISK-001",
  );
  const [severity, setSeverity] = useState("All priorities");
  const [workspaceName, setWorkspaceName] = useState("Acme Financial");
  const [draftName, setDraftName] = useState(workspaceName);
  const hasPendingSimulation = migrations.some(
    (migration) => migration.files && migration.progress < 100,
  );
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const currentMigration = selected
    ? (migrations.find((m) => m.id === selected.id) ?? selected)
    : null;

  function notify(message: string) {
    setToast(message);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 4500);
  }
  function navigate(next: View) {
    setView(next);
    setMobileNav(false);
    setModal(null);
    setNotifications(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function exportReport(migration = initialMigrations[0]) {
    downloadFile(
      `${migration.id.toLowerCase()}-sample-report.json`,
      JSON.stringify(reportFor(migration), null, 2),
    );
    notify("Sample report downloaded. All results are illustrative.");
  }
  function downloadCode() {
    const type =
      codeTab === "Java service"
        ? "PaymentService.java"
        : codeTab === "SQL schema"
          ? "customers.sql"
          : "PaymentServiceTest.java";
    downloadFile(
      type,
      codeTab === "Java service"
        ? javaCode
        : codeTab === "SQL schema"
          ? sqlCode
          : testCode,
      "text/plain",
    );
    notify("Illustrative code example downloaded.");
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        setModal((previous) => (previous === "search" ? null : "search"));
      }
      if (event.key === "Escape") {
        setNotifications(false);
        setWorkspaceMenu(false);
        setMobileNav(false);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  useEffect(() => {
    if (!hasPendingSimulation) return;
    const interval = setInterval(
      () =>
        setMigrations((items) =>
          items.map((m) =>
            m.files && m.progress < 100
              ? {
                  ...m,
                  progress: Math.min(m.progress + 20, 100),
                  status: m.progress + 20 >= 100 ? "Completed" : "In progress",
                }
              : m,
          ),
        ),
      1300,
    );
    return () => {
      clearInterval(interval);
    };
  }, [hasPendingSimulation]);

  const visibleFindings = findings.filter(
    (f) => severity === "All priorities" || f.severity === severity,
  );
  const searchResults = [
    ...nav.map((n) => ({
      title: n.name,
      detail: "Workspace page",
      view: n.name as View,
    })),
    ...migrations.map((m) => ({
      title: m.name,
      detail: `${m.id} · ${m.programs} programs`,
      migration: m,
    })),
  ].filter((item) =>
    `${item.title} ${item.detail}`.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="app-shell">
      {mobileNav && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside
        id="sidebar-navigation"
        className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}
      >
        <button
          className="brand-button"
          onClick={() => navigate("Overview")}
          aria-label="Diocle overview"
        >
          <Brand />
        </button>
        <div className="workspace-switcher-wrap">
          <button
            className="workspace-switcher"
            onClick={() => setWorkspaceMenu(!workspaceMenu)}
            aria-expanded={workspaceMenu}
          >
            <span className="workspace-avatar">
              <Layers3 size={17} />
            </span>
            <span>
              <strong>{workspaceName}</strong>
              <small>Demo workspace</small>
            </span>
            <ChevronsUpDown size={14} />
          </button>
          {workspaceMenu && (
            <div className="workspace-popover">
              <span className="eyebrow">YOUR WORKSPACES</span>
              <button onClick={() => setWorkspaceMenu(false)}>
                <Layers3 size={16} />
                {workspaceName}
                <Check size={14} />
              </button>
              <button
                onClick={() => {
                  navigate("Settings");
                  setWorkspaceMenu(false);
                }}
              >
                <Settings2 size={16} />
                Workspace settings
              </button>
            </div>
          )}
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {nav.map((item) => (
            <button
              key={item.name}
              onClick={() => navigate(item.name)}
              className={`nav-item ${view === item.name ? "active" : ""}`}
              aria-current={view === item.name ? "page" : undefined}
            >
              <item.icon size={18} />
              <span>{item.name}</span>
              {"count" in item && (
                <span className="nav-count">
                  {Math.max(0, item.count - resolved.length)}
                </span>
              )}
              {view === item.name && item.name !== "Risk findings" && (
                <span className="nav-active-dot" />
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-promo">
            <span className="promo-icon">
              <Sparkles size={17} />
            </span>
            <strong>Legacy, reimagined.</strong>
            <p>
              Decades of business logic.
              <br />A whole new possibility.
            </p>
            <button onClick={() => setModal("help")}>
              Meet your modern stack
              <ArrowUpRight size={13} />
            </button>
          </div>
          <button
            className={`nav-item ${view === "Settings" ? "active" : ""}`}
            onClick={() => navigate("Settings")}
          >
            <Settings2 size={18} />
            <span>Settings</span>
          </button>
          <button className="nav-item" onClick={() => setModal("help")}>
            <CircleHelp size={18} />
            <span>Help & documentation</span>
            <ArrowUpRight size={14} />
          </button>
          <div className="sidebar-profile">
            <button
              onClick={() => setModal("profile")}
              aria-label="View demo profile"
            >
              <span className="avatar">JD</span>
              <span>
                <strong>Jamie Davis</strong>
                <small>Workspace admin</small>
              </span>
              <ChevronsUpDown size={14} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="mobile-menu icon-button"
              onClick={() => setMobileNav(true)}
              aria-expanded={mobileNav}
              aria-controls="sidebar-navigation"
              aria-label="Open navigation"
            >
              <Menu size={20} />
            </button>
            <span className="breadcrumb-workspace">Workspace</span>
            <ChevronRight size={13} />
            <span>{view}</span>
          </div>
          <div className="topbar-actions">
            <button
              className="global-search"
              onClick={() => {
                setSearch("");
                setModal("search");
              }}
            >
              <Search size={15} />
              <span>Search anything…</span>
              <kbd>⌘ K</kbd>
            </button>
            <span className="preview-pill">
              <span />
              Demo mode
            </span>
            <div className="notification-wrap">
              <button
                className={`icon-button notification-button ${notifications ? "selected" : ""}`}
                aria-label="Notifications"
                aria-expanded={notifications}
                onClick={() => setNotifications(!notifications)}
              >
                <Bell size={18} />
                <i />
              </button>
              {notifications && (
                <div className="notifications-popover">
                  <div className="popover-heading">
                    <strong>You’re all caught up</strong>
                    <button
                      className="icon-button"
                      onClick={() => setNotifications(false)}
                      aria-label="Close notifications"
                    >
                      <X size={16} />
                    </button>
                  </div>
                  <p>Here’s what happened in your sample workspace.</p>
                  {activities.slice(0, 2).map((a) => (
                    <button
                      key={a.title}
                      onClick={() => {
                        navigate(
                          a.kind === "review"
                            ? "Risk findings"
                            : "Verification",
                        );
                      }}
                    >
                      <span className={`activity-icon ${a.kind}`}>
                        {a.kind === "review" ? (
                          <ShieldAlert size={16} />
                        ) : (
                          <CheckCheck size={16} />
                        )}
                      </span>
                      <span>
                        <strong>{a.title}</strong>
                        <small>{a.time}</small>
                      </span>
                      <ChevronRight size={14} />
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              className="avatar top-avatar"
              onClick={() => setModal("profile")}
              aria-label="Open profile"
            >
              JD
            </button>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="page-eyebrow">
                <span className="green-dot" /> YOUR MODERNIZATION WORKSPACE
              </div>
              <h1>
                {view === "Overview" ? "Make room for what’s next." : view}
              </h1>
              <p>{descriptions[view]}</p>
            </div>
            <button className="button primary" onClick={() => setModal("new")}>
              <Plus size={17} />
              New migration
            </button>
          </div>

          {view === "Overview" && (
            <div className="view-content">
              <section className="hero">
                <div className="hero-content">
                  <div className="hero-kicker">
                    <span className="hero-kicker-dot" />
                    BUILT FOR A NEW CHAPTER
                  </div>
                  <h2>
                    Keep the logic.
                    <br />
                    Leave the legacy.
                  </h2>
                  <p>
                    Turn your COBOL into modern, verified services.
                    <br />
                    With the business logic you trust, intact.
                  </p>
                  <button
                    className="hero-link"
                    onClick={() => {
                      setSelected(migrations[0]);
                    }}
                  >
                    Continue your migration
                    <ArrowRight size={16} />
                  </button>
                </div>
                <HeroArt />
                <div className="hero-bottom">
                  <span>
                    <ShieldCheck size={13} />
                    Verified by behavior. Built for confidence.
                  </span>
                  <span className="powered-by">
                    <Sparkles size={12} />
                    Powered by Muse Spark
                  </span>
                </div>
              </section>
              <div className="section-heading">
                <h2>A little perspective.</h2>
                <span>
                  Sample workspace overview
                  <CircleHelp size={13} />
                </span>
              </div>
              <Stats openFindings={3 - resolved.length} />
              <div className="overview-grid">
                <MigrationList
                  migrations={migrations}
                  onSelect={setSelected}
                  onNew={() => setModal("new")}
                />
                <ActivityList onView={() => setModal("activity")} />
              </div>
              <div className="overview-bottom-grid">
                <DependencyGraph
                  compact
                  onExplore={() => navigate("Dependency graph")}
                />
                <section className="panel confidence-panel">
                  <div className="confidence-top">
                    <span className="confidence-icon">
                      <ShieldCheck size={21} />
                    </span>
                    <span className="eyebrow">CONFIDENCE, NOT GUESSWORK</span>
                  </div>
                  <h2>
                    Modern code.
                    <br />
                    The same promise.
                  </h2>
                  <p>
                    We compare original and converted outputs, so your financial
                    logic stays true to its roots.
                  </p>
                  <div className="confidence-metric">
                    <strong>
                      96.8<span>%</span>
                    </strong>
                    <span>
                      behavioral match
                      <br />
                      in sample test results
                    </span>
                  </div>
                  <button
                    className="text-button"
                    onClick={() => navigate("Verification")}
                  >
                    Explore verification
                    <ArrowRight size={15} />
                  </button>
                </section>
              </div>
            </div>
          )}

          {view === "Migrations" && (
            <div className="view-content">
              <MigrationList
                migrations={migrations}
                onSelect={setSelected}
                onNew={() => setModal("new")}
                full
              />
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Inside the sample codebase</h2>
                    <p>
                      A closer look at core banking’s synthetic COBOL programs.
                    </p>
                  </div>
                  <Badge tone="neutral">Core banking</Badge>
                </div>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Program</th>
                        <th>Lines of code</th>
                        <th>Dependencies</th>
                        <th>Risk</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {programs.map((p) => (
                        <tr key={p.name}>
                          <td>
                            <span className="program-file">
                              <FileCode2 size={17} />
                              <span>
                                <strong>{p.name}</strong>
                                <small>{p.description}</small>
                              </span>
                            </span>
                          </td>
                          <td>{p.lines.toLocaleString()}</td>
                          <td>{p.dependencies}</td>
                          <td>
                            <Badge
                              tone={
                                p.risk === "High"
                                  ? "amber"
                                  : p.risk === "Medium"
                                    ? "purple"
                                    : "green"
                              }
                            >
                              {p.risk}
                            </Badge>
                          </td>
                          <td>{p.status}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
          )}

          {view === "Dependency graph" && (
            <div className="view-content">
              <div className="context-bar">
                <span>
                  <FolderGit2 size={17} />
                  <strong>Core banking</strong>
                  <Badge tone="neutral" dot={false}>
                    Sample graph
                  </Badge>
                </span>
                <span>
                  4 programs<span className="divider-dot">·</span>2 copybooks
                  <span className="divider-dot">·</span>6 connections
                </span>
              </div>
              <DependencyGraph />
              <div className="info-card">
                <Network size={22} />
                <div>
                  <h3>Every connection tells a story.</h3>
                  <p>
                    Select a program to inspect its details. Solid lines
                    represent CALL dependencies; dashed lines represent COPY
                    dependencies. Amber dots identify programs with risk
                    findings.
                  </p>
                </div>
              </div>
            </div>
          )}

          {view === "Risk findings" && (
            <div className="view-content">
              <div className="risk-overview">
                <div>
                  <span className="stat-icon orange">
                    <ShieldAlert size={21} />
                  </span>
                  <div>
                    <strong>{3 - resolved.length} open findings</strong>
                    <p>Review the details before moving to production.</p>
                  </div>
                </div>
                <label className="filter-select">
                  <ListFilter size={15} />
                  <select
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value)}
                    aria-label="Filter risk priority"
                  >
                    <option>All priorities</option>
                    <option>High</option>
                    <option>Medium</option>
                  </select>
                </label>
              </div>
              {visibleFindings.map((f) => (
                <section
                  className={`panel finding-card ${resolved.includes(f.id) ? "finding-resolved" : ""}`}
                  key={f.id}
                >
                  <button
                    className="finding-heading"
                    onClick={() =>
                      setExpandedFinding(expandedFinding === f.id ? null : f.id)
                    }
                    aria-expanded={expandedFinding === f.id}
                  >
                    <span
                      className={`finding-symbol ${resolved.includes(f.id) ? "green" : "orange"}`}
                    >
                      {resolved.includes(f.id) ? (
                        <CircleCheck size={20} />
                      ) : (
                        <ShieldAlert size={20} />
                      )}
                    </span>
                    <span>
                      <span className="finding-meta">
                        {f.id} <span>·</span> {f.category}
                      </span>
                      <strong>{f.title}</strong>
                    </span>
                    <Badge
                      tone={
                        resolved.includes(f.id)
                          ? "green"
                          : f.severity === "High"
                            ? "amber"
                            : "purple"
                      }
                    >
                      {resolved.includes(f.id)
                        ? "Reviewed"
                        : `${f.severity} priority`}
                    </Badge>
                    <ChevronDown
                      size={18}
                      className={expandedFinding === f.id ? "rotate" : ""}
                    />
                  </button>
                  {expandedFinding === f.id && (
                    <div className="finding-body">
                      <p>{f.description}</p>
                      <div className="finding-code">
                        <span>
                          <FileCode2 size={14} />
                          {f.program}
                          <small>Line {f.line}</small>
                        </span>
                        <code>{f.example}</code>
                      </div>
                      <div className="finding-actions">
                        <span>
                          Review state is kept for this preview session.
                        </span>
                        <button
                          className={`button ${resolved.includes(f.id) ? "secondary" : "primary"}`}
                          onClick={() => {
                            setResolved((previous) =>
                              previous.includes(f.id)
                                ? previous.filter((id) => id !== f.id)
                                : [...previous, f.id],
                            );
                            notify(
                              resolved.includes(f.id)
                                ? "Finding reopened in this preview."
                                : "Finding marked as reviewed in this preview.",
                            );
                          }}
                        >
                          <Check size={15} />
                          {resolved.includes(f.id)
                            ? "Reopen finding"
                            : "Mark as reviewed"}
                        </button>
                      </div>
                    </div>
                  )}
                </section>
              ))}
              <DemoNote />
            </div>
          )}

          {view === "Conversions" && (
            <div className="view-content">
              <div className="conversion-stats">
                {[
                  {
                    icon: Braces,
                    count: "32",
                    title: "Java services",
                    sub: "Business logic, translated",
                  },
                  {
                    icon: Database,
                    count: "13",
                    title: "SQL schemas",
                    sub: "From copybooks to tables",
                  },
                  {
                    icon: ShieldCheck,
                    count: "96",
                    title: "Test examples",
                    sub: "Generated test scenarios",
                  },
                ].map((s) => (
                  <div className="panel" key={s.title}>
                    <span className="stat-icon green">
                      <s.icon size={21} />
                    </span>
                    <strong>{s.count}</strong>
                    <div>
                      <h3>{s.title}</h3>
                      <p>{s.sub}</p>
                    </div>
                  </div>
                ))}
              </div>
              <CodePreview
                tab={codeTab}
                onTab={setCodeTab}
                onDownload={downloadCode}
              />
              <div className="info-card">
                <Sparkles size={22} />
                <div>
                  <h3>Designed for Muse Spark.</h3>
                  <p>
                    The production converter will use Muse Spark through the
                    Meta Model API. This frontend shows handwritten,
                    illustrative outputs; it does not call a model.
                  </p>
                </div>
              </div>
            </div>
          )}

          {view === "Verification" && (
            <div className="view-content">
              <VerificationView
                onReport={() => {
                  downloadFile(
                    "workspace-verification-sample.json",
                    JSON.stringify(
                      {
                        mock: true,
                        disclaimer:
                          "Synthetic frontend preview. No real verification has been performed.",
                        illustrativeSummary: {
                          total: 1000,
                          passed: 968,
                          failed: 32,
                        },
                        migrations: initialMigrations
                          .slice(0, 2)
                          .map(reportFor),
                      },
                      null,
                      2,
                    ),
                  );
                  notify("Workspace sample verification report downloaded.");
                }}
              />
            </div>
          )}

          {view === "Delivery" && (
            <div className="view-content">
              <DeliveryView />
            </div>
          )}

          {view === "Live runs" && (
            <div className="view-content">
              <RunsView />
            </div>
          )}

          {view === "Reports" && (
            <div className="view-content">
              <div className="report-intro">
                <span className="report-intro-icon">
                  <FileText size={27} />
                </span>
                <div>
                  <h2>The full picture, ready to share.</h2>
                  <p>
                    Explore migration summaries or download clearly labeled
                    sample JSON reports.
                  </p>
                </div>
              </div>
              <div className="reports-grid">
                {migrations.map((m) => (
                  <section className="panel report-card" key={m.id}>
                    <div className="report-card-top">
                      <span className={`migration-icon ${m.color}`}>
                        <FileText size={23} />
                      </span>
                      <Badge
                        tone={m.status === "Completed" ? "green" : "neutral"}
                      >
                        {m.status === "Completed" ? "Ready" : "Preview"}
                      </Badge>
                    </div>
                    <span className="eyebrow">{m.id} · SAMPLE REPORT</span>
                    <h2>{m.name}</h2>
                    <p>{m.description}</p>
                    <div className="report-card-stats">
                      <span>
                        <strong>{m.programs}</strong>Programs
                      </span>
                      <span>
                        <strong>{m.copybooks}</strong>Copybooks
                      </span>
                      <span>
                        <strong>{m.progress}%</strong>Progress
                      </span>
                    </div>
                    <button
                      className="button secondary"
                      onClick={() => exportReport(m)}
                    >
                      <ArrowDownToLine size={15} />
                      Download sample JSON
                    </button>
                  </section>
                ))}
              </div>
              <DemoNote />
            </div>
          )}

          {view === "Settings" && (
            <div className="view-content">
              <section className="panel settings-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Workspace details</h2>
                    <p>A home for your next chapter.</p>
                  </div>
                </div>
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    setWorkspaceName(draftName.trim() || "Acme Financial");
                    notify("Workspace name updated for this preview session.");
                  }}
                >
                  <label className="form-label">
                    Workspace name
                    <input
                      value={draftName}
                      maxLength={35}
                      onChange={(e) => setDraftName(e.target.value)}
                      required
                    />
                  </label>
                  <label className="form-label">
                    Environment
                    <input
                      value="Frontend preview · Browser session only"
                      disabled
                    />
                  </label>
                  <div className="settings-model">
                    <Sparkles size={22} />
                    <div>
                      <strong>Muse Spark</strong>
                      <p>Planned conversion model · Meta Model API</p>
                    </div>
                    <Badge tone="neutral">Not connected</Badge>
                  </div>
                  <button className="button primary" type="submit">
                    Save changes
                    <Check size={15} />
                  </button>
                </form>
              </section>
              <section className="panel settings-panel">
                <div className="panel-heading">
                  <div>
                    <h2>About this preview</h2>
                    <p>
                      Built to explore what the finished Diocle workspace could
                      feel like.
                    </p>
                  </div>
                </div>
                <div className="settings-about">
                  <p>
                    No backend services are connected. File selections stay in
                    the browser, new migrations run a visual simulation, and all
                    findings and verification results are synthetic. Refreshing
                    resets this workspace.
                  </p>
                  <button
                    className="button secondary"
                    onClick={() => {
                      setMigrations(initialMigrations);
                      setResolved([]);
                      setWorkspaceName("Acme Financial");
                      setDraftName("Acme Financial");
                      notify("The demo workspace has been reset.");
                    }}
                  >
                    Reset demo workspace
                  </button>
                </div>
              </section>
            </div>
          )}

          <footer className="page-footer">
            <span>
              <Brand small />
              Thoughtfully modernized.
            </span>
            <span>
              <span className="footer-status" />
              Frontend preview<span className="divider-dot">·</span>All data is
              synthetic
            </span>
            <span>
              Made for what’s next.
              <ArrowUpRight size={12} />
            </span>
          </footer>
        </main>
      </div>

      {modal === "new" && (
        <UploadModal
          onClose={() => setModal(null)}
          onCreate={(name, files) => {
            const next: Migration = {
              id: `MIG-${String(migrations.length + 1).padStart(3, "0")}`,
              name,
              description: "Locally selected files · Simulated migration",
              programs: files.filter((f) => /\.(cbl|cob)$/i.test(f)).length,
              copybooks: files.filter((f) => /\.(cpy|copy)$/i.test(f)).length,
              status: "In progress",
              progress: 0,
              updated: "Just now",
              color: "green",
              files,
            };
            setMigrations((items) => [next, ...items]);
            setModal(null);
            setView("Migrations");
            notify(
              "Preview migration created. The pipeline animation is simulated.",
            );
          }}
        />
      )}
      {modal === "search" && (
        <Modal
          title="Find your next step."
          subtitle="Search pages and migrations in this workspace."
          onClose={() => setModal(null)}
        >
          <div className="search-dialog-input">
            <Search size={19} />
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search anything…"
              aria-label="Search workspace"
            />
            <kbd>ESC</kbd>
          </div>
          <div className="search-results">
            {searchResults.length ? (
              searchResults.map((result) => (
                <button
                  key={result.title}
                  onClick={() => {
                    if ("migration" in result && result.migration) {
                      setSelected(result.migration);
                      setModal(null);
                    } else if ("view" in result && result.view)
                      navigate(result.view);
                  }}
                >
                  <span className="search-result-icon">
                    {"migration" in result ? (
                      <FolderGit2 size={18} />
                    ) : (
                      <LayoutDashboard size={18} />
                    )}
                  </span>
                  <span>
                    <strong>{result.title}</strong>
                    <small>{result.detail}</small>
                  </span>
                  <ArrowUpRight size={16} />
                </button>
              ))
            ) : (
              <div className="empty-state">
                <Search size={24} />
                <h3>No matches yet.</h3>
                <p>Try “banking”, “verification”, or “reports”.</p>
              </div>
            )}
          </div>
        </Modal>
      )}
      {modal === "activity" && (
        <Modal
          title="Your workspace, in motion."
          subtitle="A timeline of illustrative activity."
          onClose={() => setModal(null)}
        >
          <ActivityList long />
          <DemoNote compact />
        </Modal>
      )}
      {modal === "help" && (
        <Modal
          title="A new chapter for your code."
          subtitle="Meet Diocle, your COBOL modernization workspace."
          onClose={() => setModal(null)}
        >
          <div className="help-content">
            <Pipeline active={5} />
            <p>
              Bring your COBOL programs and copybooks. Diocle is designed to map
              dependencies, surface sensitive financial logic, and convert your
              code into Java services and SQL schemas using Muse Spark.
            </p>
            <p>
              The verifier will compile the original with GnuCOBOL and compare
              outputs against the converted services using the same inputs.
            </p>
            <div className="help-links">
              <button onClick={() => navigate("Dependency graph")}>
                <Network size={19} />
                <span>
                  Understand your codebase
                  <small>Explore program and copybook relationships</small>
                </span>
                <ArrowUpRight size={16} />
              </button>
              <button onClick={() => navigate("Verification")}>
                <ShieldCheck size={19} />
                <span>
                  Build confidence in the result
                  <small>Inspect sample differential test outputs</small>
                </span>
                <ArrowUpRight size={16} />
              </button>
            </div>
            <DemoNote />
          </div>
        </Modal>
      )}
      {modal === "profile" && (
        <Modal
          title="Your demo profile"
          subtitle="An illustrative workspace administrator."
          onClose={() => setModal(null)}
        >
          <div className="profile-content">
            <span className="avatar avatar-large">JD</span>
            <h3>Jamie Davis</h3>
            <p>Workspace admin · {workspaceName}</p>
            <Badge tone="neutral">Synthetic identity</Badge>
            <button
              className="button secondary"
              onClick={() => navigate("Settings")}
            >
              <Settings2 size={16} />
              Workspace settings
            </button>
          </div>
        </Modal>
      )}
      {currentMigration && (
        <Modal
          title={currentMigration.name}
          subtitle={`${currentMigration.id} · ${currentMigration.description}`}
          onClose={() => setSelected(null)}
          wide
        >
          <div className="migration-detail">
            <div className="detail-status">
              <Badge
                tone={
                  currentMigration.status === "Completed"
                    ? "green"
                    : currentMigration.status === "Needs review"
                      ? "amber"
                      : "blue"
                }
              >
                {currentMigration.status}
              </Badge>
              <span>
                {currentMigration.programs} programs
                <span className="divider-dot">·</span>
                {currentMigration.copybooks} copybooks
              </span>
            </div>
            <div className="detail-progress">
              <Progress value={currentMigration.progress} />
              <strong>{currentMigration.progress}%</strong>
            </div>
            <Pipeline
              active={
                currentMigration.progress === 100
                  ? 5
                  : currentMigration.progress >= 75
                    ? 3
                    : currentMigration.progress >= 40
                      ? 2
                      : 1
              }
            />
            {currentMigration.files ? (
              <div className="uploaded-files">
                <h3>Selected files</h3>
                {currentMigration.files.map((file, index) => (
                  <span key={`${file}-${index}`}>
                    <FileCode2 size={16} />
                    {file}
                  </span>
                ))}
                <p>
                  This is a visual simulation. No files were uploaded or
                  analyzed.
                </p>
              </div>
            ) : (
              <div className="detail-grid">
                <div>
                  <span className="stat-icon green">
                    <Braces size={20} />
                  </span>
                  <strong>
                    {currentMigration.id === "MIG-003"
                      ? 18
                      : currentMigration.id === "MIG-002"
                        ? 12
                        : 2}
                  </strong>
                  <span>Example services</span>
                </div>
                <div>
                  <span className="stat-icon purple">
                    <Database size={20} />
                  </span>
                  <strong>{currentMigration.copybooks}</strong>
                  <span>Example schemas</span>
                </div>
                <div>
                  <span className="stat-icon orange">
                    <ShieldAlert size={20} />
                  </span>
                  <strong>{currentMigration.id === "MIG-003" ? 3 : 0}</strong>
                  <span>Sample findings</span>
                </div>
              </div>
            )}
            <DemoNote />
            <div className="modal-actions">
              <button
                className="button secondary"
                onClick={() => exportReport(currentMigration)}
              >
                <Download size={15} />
                Export sample report
              </button>
              <button
                className="button primary"
                onClick={() => {
                  setSelected(null);
                  navigate(
                    currentMigration.status === "Needs review"
                      ? "Risk findings"
                      : currentMigration.status === "Completed"
                        ? "Verification"
                        : "Dependency graph",
                  );
                }}
              >
                {currentMigration.status === "Needs review"
                  ? "Review findings"
                  : currentMigration.status === "Completed"
                    ? "Explore verification"
                    : "Explore sample analysis"}
                <ArrowRight size={15} />
              </button>
            </div>
          </div>
        </Modal>
      )}
      {toast && (
        <div className="toast" role="status">
          <CircleCheck size={19} />
          <span>{toast}</span>
          <button
            onClick={() => setToast("")}
            aria-label="Dismiss notification"
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}

function UploadModal({
  onClose,
  onCreate,
}: {
  onClose: () => void;
  onCreate: (name: string, files: string[]) => void;
}) {
  const [name, setName] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  function selectFiles(selected: FileList | null) {
    if (!selected) return;
    const items = Array.from(selected);
    const valid = items.filter((file) =>
      /\.(cbl|cob|cpy|copy)$/i.test(file.name),
    );
    setError(
      valid.length !== items.length
        ? "Only COBOL (.cbl, .cob) and copybook (.cpy, .copy) files are supported."
        : "",
    );
    setFiles((previous) => [
      ...new Set([...previous, ...valid.map((file) => file.name)]),
    ]);
  }
  return (
    <Modal
      title="Something new starts here."
      subtitle="Create a migration and explore the modernization journey."
      onClose={onClose}
    >
      <form
        className="upload-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) {
            setError("Give your migration a name before starting.");
            return;
          }
          if (!files.some((file) => /\.(cbl|cob)$/i.test(file))) {
            setError(
              "Add at least one COBOL program, or use the synthetic sample below.",
            );
            return;
          }
          onCreate(name.trim(), files);
        }}
      >
        <label className="form-label">
          Migration name
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Customer account services"
            maxLength={60}
            required
          />
        </label>
        <div
          className={`drop-zone ${dragging ? "dragging" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            selectFiles(event.dataTransfer.files);
          }}
        >
          <span className="upload-icon">
            <Upload size={25} />
          </span>
          <strong>Give your legacy a new beginning.</strong>
          <p>Drop COBOL programs and copybooks here</p>
          <button
            type="button"
            className="button secondary"
            onClick={() => fileInput.current?.click()}
          >
            Browse files
            <Plus size={14} />
          </button>
          <small>
            .cbl, .cob, .cpy, .copy · File names stay in your browser
          </small>
          <input
            className="sr-only"
            ref={fileInput}
            type="file"
            multiple
            accept=".cbl,.cob,.cpy,.copy"
            onChange={(event) => {
              selectFiles(event.target.files);
              event.target.value = "";
            }}
            aria-label="Choose COBOL and copybook files"
          />
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {files.length > 0 && (
          <div className="selected-files">
            {files.map((file) => (
              <div key={file}>
                <FileCode2 size={16} />
                <span>{file}</span>
                <button
                  type="button"
                  className="icon-button"
                  aria-label={`Remove ${file}`}
                  onClick={() =>
                    setFiles((previous) => previous.filter((f) => f !== file))
                  }
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
        <button
          className="sample-button"
          type="button"
          onClick={() => {
            setFiles(["ACCT-MAIN.cbl", "PAYMENT-PROC.cbl", "CUSTOMER.cpy"]);
            setName((previous) => previous || "Customer account services");
            setError("");
          }}
        >
          <Sparkles size={17} />
          <span>
            Just looking around? <strong>Use a synthetic sample</strong>
          </span>
          <ArrowRight size={15} />
        </button>
        <DemoNote />
        <div className="modal-actions">
          <button className="button secondary" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="button primary" type="submit">
            Start preview migration
            <ArrowRight size={16} />
          </button>
        </div>
      </form>
    </Modal>
  );
}
