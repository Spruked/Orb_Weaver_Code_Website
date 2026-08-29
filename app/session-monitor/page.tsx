import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Database,
  Fingerprint,
  GitBranch,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { getSessionMonitorDashboard, type CorrelationStatus } from "../../lib/session-monitor";

export const dynamic = "force-dynamic";

function shortValue(value: string | null) {
  if (!value) {
    return "Unknown";
  }

  if (value.length > 42) {
    return `${value.slice(0, 18)}...${value.slice(-16)}`;
  }

  return value;
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "Unknown";
  }

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusLabel(status: CorrelationStatus) {
  if (status === "match") {
    return "Match";
  }

  if (status === "mismatch") {
    return "Mismatch";
  }

  return "Unknown";
}

function StatusIcon({ status }: { status: CorrelationStatus }) {
  if (status === "match") {
    return <CheckCircle2 aria-hidden="true" />;
  }

  if (status === "mismatch") {
    return <AlertTriangle aria-hidden="true" />;
  }

  return <CircleHelp aria-hidden="true" />;
}

export default async function SessionMonitorPage() {
  const dashboard = await getSessionMonitorDashboard();
  const latestSession = dashboard.sessions[0] ?? null;
  const sourceEntries = Object.entries(dashboard.sourceHealth);
  const artifacts = dashboard.cipher.artifacts;
  const timelineItems = dashboard.timeline?.timeline.slice(-12).reverse() ?? [];
  const reloadWindows = dashboard.timeline?.reload_quota_windows.slice(-4).reverse() ?? [];

  return (
    <section className="section session-monitor-page">
      <div className="container monitor-stack">
        <div className="monitor-hero">
          <div>
            <p className="eyebrow">Operational Dashboard</p>
            <h1>Session Monitor</h1>
            <p>
              Runtime evidence stays in the monitor. Artifact evidence stays in
              Code Cipher. This dashboard only correlates the two records.
            </p>
          </div>
          <a href="/session-monitor" className="button button-primary">
            <RefreshCw size={17} aria-hidden="true" />
            Refresh
          </a>
        </div>

        {!dashboard.monitorOnline ? (
          <div className="monitor-alert">
            <AlertTriangle aria-hidden="true" />
            <div>
              <strong>Session Monitor API is offline</strong>
              <span>Start the local FastAPI service at {dashboard.monitorApiUrl}.</span>
            </div>
          </div>
        ) : null}

        {dashboard.mismatchCount > 0 ? (
          <div className="monitor-alert monitor-alert-danger">
            <AlertTriangle aria-hidden="true" />
            <div>
              <strong>Evidence mismatch</strong>
              <span>Release provenance cannot be verified until these values agree.</span>
            </div>
          </div>
        ) : null}

        <div className="monitor-grid monitor-grid-3">
          <article className="monitor-card">
            <div className="monitor-card-heading">
              <Activity aria-hidden="true" />
              <h2>Session</h2>
            </div>
            <dl className="monitor-facts">
              <div>
                <dt>Session ID</dt>
                <dd>{shortValue(latestSession?.id ?? null)}</dd>
              </div>
              <div>
                <dt>Workspace</dt>
                <dd>{shortValue(latestSession?.workspace_path ?? null)}</dd>
              </div>
              <div>
                <dt>Started</dt>
                <dd>{formatDate(latestSession?.started_at)}</dd>
              </div>
              <div>
                <dt>Quota</dt>
                <dd>{dashboard.quota.status}</dd>
              </div>
            </dl>
          </article>

          <article className="monitor-card">
            <div className="monitor-card-heading">
              <GitBranch aria-hidden="true" />
              <h2>Git</h2>
            </div>
            <dl className="monitor-facts">
              <div>
                <dt>Branch</dt>
                <dd>{shortValue(latestSession?.branch ?? null)}</dd>
              </div>
              <div>
                <dt>HEAD</dt>
                <dd>{shortValue(latestSession?.head ?? null)}</dd>
              </div>
              <div>
                <dt>Remote</dt>
                <dd>{shortValue(latestSession?.remote ?? null)}</dd>
              </div>
              <div>
                <dt>Remote Host</dt>
                <dd>{shortValue(latestSession?.remote_host ?? null)}</dd>
              </div>
            </dl>
          </article>

          <article className="monitor-card">
            <div className="monitor-card-heading">
              <ShieldCheck aria-hidden="true" />
              <h2>Code Cipher</h2>
            </div>
            <dl className="monitor-facts">
              <div>
                <dt>Release</dt>
                <dd>{dashboard.cipher.release_id}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{dashboard.cipher.version}</dd>
              </div>
              <div>
                <dt>Source HEAD</dt>
                <dd>{shortValue(dashboard.cipher.source.git_commit)}</dd>
              </div>
              <div>
                <dt>Verification</dt>
                <dd>{dashboard.cipher.source.verification_result}</dd>
              </div>
            </dl>
          </article>
        </div>

        <div className="monitor-grid">
          <article className="monitor-card">
            <div className="monitor-card-heading">
              <Fingerprint aria-hidden="true" />
              <h2>Evidence Correlation</h2>
            </div>
            <div className="correlation-table">
              {dashboard.correlations.map((item) => (
                <div className={`correlation-row is-${item.status}`} key={item.label}>
                  <div className="correlation-status">
                    <StatusIcon status={item.status} />
                    <span>{statusLabel(item.status)}</span>
                  </div>
                  <strong>{item.label}</strong>
                  <code>{shortValue(item.monitorValue)}</code>
                  <code>{shortValue(item.cipherValue)}</code>
                </div>
              ))}
            </div>
          </article>

          <article className="monitor-card">
            <div className="monitor-card-heading">
              <Database aria-hidden="true" />
              <h2>Evidence Sources</h2>
            </div>
            <div className="source-list">
              {sourceEntries.length > 0 ? (
                sourceEntries.map(([source, record]) => (
                  <div className="source-row" key={source}>
                    <div>
                      <strong>{source}</strong>
                      <span>{record.category} / {record.evidence_class}</span>
                    </div>
                    <time>{formatDate(record.last_seen)}</time>
                  </div>
                ))
              ) : (
                <p className="muted-copy">No monitor evidence has been observed yet.</p>
              )}
            </div>
          </article>
        </div>

        <article className="monitor-card">
          <div className="monitor-card-heading">
            <ShieldCheck aria-hidden="true" />
            <h2>Protected Artifacts</h2>
          </div>
          <div className="artifact-grid">
            {artifacts.map((artifact) => (
              <div className="artifact-row" key={artifact.id}>
                <strong>{artifact.filename}</strong>
                <span>{artifact.platform}</span>
                <code>{artifact.sha256}</code>
              </div>
            ))}
          </div>
        </article>

        <div className="monitor-grid">
          <article className="monitor-card">
            <div className="monitor-card-heading">
              <Activity aria-hidden="true" />
              <h2>Session Timeline</h2>
            </div>
            <div className="timeline-list">
              {timelineItems.length > 0 ? (
                timelineItems.map((item) => (
                  <div className="timeline-row" key={`${item.timestamp}-${item.event_type}-${item.source_identifier}`}>
                    <time>{formatDate(item.timestamp)}</time>
                    <strong>{item.event_type}</strong>
                    <span>{item.summary}</span>
                    {item.quota ? (
                      <code>
                        primary {item.quota.primary_used_percent ?? "?"}% / secondary{" "}
                        {item.quota.secondary_used_percent ?? "?"}%
                      </code>
                    ) : null}
                    {item.rollout?.duration_ms || item.rollout?.last_token_usage?.total_tokens ? (
                      <code>
                        {item.rollout.duration_ms ? `${item.rollout.duration_ms}ms` : "duration ?"} /{" "}
                        {item.rollout.last_token_usage?.total_tokens ?? "?"} tokens
                      </code>
                    ) : null}
                  </div>
                ))
              ) : (
                <p className="muted-copy">No correlated monitor events are available yet.</p>
              )}
            </div>
          </article>

          <article className="monitor-card">
            <div className="monitor-card-heading">
              <AlertTriangle aria-hidden="true" />
              <h2>Reload Impact</h2>
            </div>
            <div className="reload-list">
              {reloadWindows.length > 0 ? (
                reloadWindows.map((window) => (
                  <div className="reload-row" key={`${window.reload_event.timestamp}-${window.reload_event.source_identifier}`}>
                    <strong>{window.reload_event.event_type}</strong>
                    <time>{formatDate(window.reload_event.timestamp)}</time>
                    <span>{window.reload_event.summary}</span>
                    <code>
                      Δ primary {window.quota_delta.primary_used_percent ?? "?"}% / Δ secondary{" "}
                      {window.quota_delta.secondary_used_percent ?? "?"}%
                    </code>
                  </div>
                ))
              ) : (
                <p className="muted-copy">No reload-to-quota windows have been observed yet.</p>
              )}
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}
