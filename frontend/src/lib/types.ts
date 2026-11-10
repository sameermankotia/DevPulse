/** Mirrors the response models in backend/app/schemas/api.py. */

export type Band = 'elite' | 'high' | 'medium' | 'low'
export type Severity = 'critical' | 'elevated' | 'healthy'
export type StageKey = 'code' | 'pickup' | 'review' | 'rework' | 'release'

export interface Repository {
  id: number
  full_name: string
  default_branch: string
  is_private: boolean
  last_synced_at: string | null
}

export interface MetricPoint {
  at: string
  value: number
}

export interface Metric {
  key: 'deployment_frequency' | 'lead_time' | 'change_failure_rate' | 'time_to_restore'
  label: string
  unit: 'per_day' | 'seconds' | 'ratio'
  value: number | null
  band: Band | null
  trend: number | null
  higher_is_better: boolean
  sample_count: number
  series: MetricPoint[]
}

export interface Stage {
  stage: StageKey
  label: string
  description: string
  is_queue: boolean
  sample_count: number
  p50_seconds: number | null
  p75_seconds: number | null
  p90_seconds: number | null
  share_of_pipeline: number
}

export interface Bottleneck {
  stage: StageKey
  label: string
  severity: Severity
  p50_seconds: number
  p90_seconds: number
  threshold_seconds: number
  overage: number
  is_queue: boolean
  sample_count: number
  share_of_pipeline: number
  evidence_pr_numbers: number[]
}

export interface CiHealth {
  median_duration_seconds: number | null
  p90_duration_seconds: number | null
  success_rate: number | null
  flake_rate: number | null
  total_runs: number
}

export interface Snapshot {
  repository: Repository
  window_days: number
  window_start: string
  window_end: string
  metrics: Metric[]
  stages: Stage[]
  bottlenecks: Bottleneck[]
  ci: CiHealth
  pull_request_count: number
  contributor_count: number
  median_pr_size: number | null
}

export interface PullRequestRow {
  number: number
  title: string
  author: string
  state: string
  opened_at: string
  merged_at: string | null
  additions: number
  deletions: number
  changed_files: number
  stages: Partial<Record<StageKey, number>>
  lead_time_seconds: number | null
}

export interface Recommendation {
  title: string
  stage: string
  impact: 'high' | 'medium' | 'low'
  effort: 'low' | 'medium' | 'high'
  rationale: string
  expected_effect: string
  ai_assisted: boolean
  ai_note: string
}

export interface Insight {
  id: number
  repository_id: number
  window_days: number
  model: string
  created_at: string
  headline: string
  summary: string
  confidence: string
  recommendations: Recommendation[]
  risks: string[]
  latency_ms: number | null
}

export interface Health {
  status: 'ok' | 'degraded'
  environment: string
  database: boolean
  llm_configured: boolean
  demo_mode: boolean
}
