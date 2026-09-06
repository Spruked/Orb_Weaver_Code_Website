export type TelemetryConfidence =
  | "OBSERVED"
  | "ATTRIBUTED"
  | "DERIVED"
  | "UNATTRIBUTED"
  | "UNAVAILABLE";

export type EnvironmentType =
  | "desktop_editor"
  | "cli_agent"
  | "application"
  | "container"
  | "remote_workspace"
  | "unknown";

export type SupportedProvider =
  | "openai"
  | "anthropic"
  | "gemini"
  | "xai"
  | "local_ollama"
  | "unknown";

export interface EnvironmentContext {
  environment_id: string;
  environment_type: EnvironmentType;
  editor_name?: string;
  editor_process_name?: string;
  window_handle?: string;
  process_id?: string;
  window_title?: string;
  workspace_path?: string;
  workspace_name?: string;
  project?: string;
  is_active: boolean;
  started_at_utc?: string;
  last_seen_utc: string;
}

export interface TokenMetrics {
  input_tokens?: number;
  cached_tokens?: number;
  cache_creation_tokens?: number;
  output_tokens?: number;
  reasoning_tokens?: number;
  total_tokens?: number;
  request_count: number;
  cost_amount?: string;
  cost_currency?: string;
  cost_source?: "provider_response" | "invoice" | "manual" | "estimate";
  provider_fields?: Record<string, number | string | null>;
}

export interface AccountQuotaMetrics {
  scope: "shared_account";
  provider: SupportedProvider;
  five_hour_used_percent?: number;
  weekly_used_percent?: number;
  monthly_used_percent?: number;
  reset_timestamp_utc?: string;
  evidence_confidence: "OBSERVED" | "UNATTRIBUTED" | "UNAVAILABLE";
}

export interface EvidenceAnchor {
  code_vin?: string;
  commit_hash?: string;
  merkle_root?: string;
  cipher_signature?: string;
}

export interface TelemetryEvent {
  event_id: string;
  session_id: string;
  timestamp_utc: string;
  confidence: TelemetryConfidence;
  environment: EnvironmentContext;
  provider: {
    name: SupportedProvider;
    model?: string;
    endpoint?: string;
    request_id?: string;
    evidence_source: string;
  };
  usage?: TokenMetrics;
  quota?: AccountQuotaMetrics;
  evidence_anchor?: EvidenceAnchor;
}
