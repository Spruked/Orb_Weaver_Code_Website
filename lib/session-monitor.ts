import { releaseManifest } from "./release-manifest";

const DEFAULT_MONITOR_API_URL = "http://127.0.0.1:18441";

export type MonitorSession = {
  id: string;
  workspace_path: string;
  source: string;
  started_at: string;
  ended_at: string | null;
  repo_root: string | null;
  branch: string | null;
  head: string | null;
  remote: string | null;
  remote_host: string | null;
};

export type MonitorQuota = {
  status: string;
  remaining?: number;
  limit?: number;
  reset_at?: string;
  observed_via?: string;
};

export type MonitorToday = {
  sessions: MonitorSession[];
  session_count: number;
  quota: MonitorQuota;
};

export type EvidenceSourceHealth = Record<
  string,
  {
    last_seen: string;
    evidence_class: string;
    category: string;
  }
>;

export type TimelineQuota = {
  primary_used_percent: number | null;
  secondary_used_percent: number | null;
  resets_at: string | null;
  source_file: string | null;
};

export type TimelineItem = {
  timestamp: string;
  session_id: string;
  category: string;
  event_type: string;
  source: string;
  source_identifier: string;
  evidence_class: string;
  parser_version: string;
  summary: string;
  quota?: TimelineQuota;
  rollout?: {
    duration_ms?: number | null;
    error?: string | null;
    turn_id?: string | null;
    started_at?: number | null;
    started_at_ms?: number | null;
    model_context_window?: number | null;
    collaboration_mode_kind?: string | null;
    last_token_usage?: Record<string, number | null>;
    total_token_usage?: Record<string, number | null>;
    source_file?: string;
  };
};

export type ReloadQuotaWindow = {
  reload_event: TimelineItem;
  quota_before: TimelineItem | null;
  quota_after: TimelineItem | null;
  quota_delta: {
    primary_used_percent: number | null;
    secondary_used_percent: number | null;
  };
};

export type MonitorTimeline = {
  correlation_version: string;
  event_count: number;
  counts: Record<string, number>;
  timeline: TimelineItem[];
  reload_quota_windows: ReloadQuotaWindow[];
  token_usage_summary?: {
    attributed_last_usage_turn_count: number;
    unattributed_last_usage_record_count: number;
    summed_last_token_usage: Record<string, number>;
    cumulative_snapshot_count: number;
    latest_total_token_usage: Record<string, number | null> | null;
    max_total_tokens: number | null;
  };
};

export type CorrelationStatus = "match" | "mismatch" | "unknown";

export type EvidenceCorrelation = {
  label: string;
  monitorValue: string | null;
  cipherValue: string | null;
  status: CorrelationStatus;
};

export type SessionMonitorDashboard = {
  monitorOnline: boolean;
  monitorApiUrl: string;
  sessions: MonitorSession[];
  quota: MonitorQuota;
  sourceHealth: EvidenceSourceHealth;
  timeline: MonitorTimeline | null;
  cipher: typeof releaseManifest;
  correlations: EvidenceCorrelation[];
  mismatchCount: number;
};

function sameOrUnknown(monitorValue: string | null, cipherValue: string | null): CorrelationStatus {
  if (!monitorValue || !cipherValue) {
    return "unknown";
  }

  return monitorValue === cipherValue ? "match" : "mismatch";
}

function repositoryStatus(monitorValue: string | null, cipherValue: string | null): CorrelationStatus {
  if (!monitorValue || !cipherValue) {
    return "unknown";
  }

  const monitorName = monitorValue.split(/[\\/]/).filter(Boolean).at(-1);
  const cipherName = cipherValue.split(/[\\/]/).filter(Boolean).at(-1);

  return monitorName === cipherName ? "match" : "mismatch";
}

function valueOrNull(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

async function readMonitorJson<T>(apiUrl: string, path: string): Promise<T | null> {
  try {
    const response = await fetch(`${apiUrl}${path}`, {
      cache: "no-store",
    });

    if (!response.ok) {
      return null;
    }

    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export async function getSessionMonitorDashboard(): Promise<SessionMonitorDashboard> {
  const monitorApiUrl = process.env.SESSION_MONITOR_API_URL ?? DEFAULT_MONITOR_API_URL;
  const [today, sourceHealth, timeline] = await Promise.all([
    readMonitorJson<MonitorToday>(monitorApiUrl, "/today"),
    readMonitorJson<EvidenceSourceHealth>(monitorApiUrl, "/evidence/sources"),
    readMonitorJson<MonitorTimeline>(monitorApiUrl, "/timeline?limit=80"),
  ]);

  const sessions = today?.sessions ?? [];
  const latestSession = sessions[0] ?? null;
  const cipherSource = releaseManifest.source;
  const monitorRepository = valueOrNull(latestSession?.repo_root);
  const cipherRepository = valueOrNull(cipherSource.repository);
  const monitorHead = valueOrNull(latestSession?.head);
  const cipherHead = valueOrNull(cipherSource.git_commit);

  const correlations: EvidenceCorrelation[] = [
    {
      label: "Repository",
      monitorValue: monitorRepository,
      cipherValue: cipherRepository,
      status: repositoryStatus(monitorRepository, cipherRepository),
    },
    {
      label: "Git Commit",
      monitorValue: monitorHead,
      cipherValue: cipherHead,
      status: sameOrUnknown(monitorHead, cipherHead),
    },
    {
      label: "Source Manifest",
      monitorValue: null,
      cipherValue: valueOrNull(cipherSource.source_manifest_hash),
      status: "unknown",
    },
    {
      label: "Release Identity",
      monitorValue: null,
      cipherValue: valueOrNull(releaseManifest.release_id),
      status: "unknown",
    },
  ];

  return {
    monitorOnline: today !== null,
    monitorApiUrl,
    sessions,
    quota: today?.quota ?? { status: "unknown" },
    sourceHealth: sourceHealth ?? {},
    timeline,
    cipher: releaseManifest,
    correlations,
    mismatchCount: correlations.filter((item) => item.status === "mismatch").length,
  };
}
