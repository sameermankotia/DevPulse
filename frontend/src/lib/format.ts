import type { Band, Metric, Severity } from './types'

const MINUTE = 60
const HOUR = 3600
const DAY = 86400

/**
 * Durations read the way engineers say them out loud: "4h", "2d 6h", "18m".
 * Precision drops as magnitude grows, because nobody needs the minutes on a
 * three-day wait.
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '—'
  if (seconds < MINUTE) return `${Math.round(seconds)}s`
  if (seconds < HOUR) return `${Math.round(seconds / MINUTE)}m`

  if (seconds < DAY) {
    const hours = Math.floor(seconds / HOUR)
    const minutes = Math.round((seconds % HOUR) / MINUTE)
    return minutes > 0 && hours < 10 ? `${hours}h ${minutes}m` : `${hours}h`
  }

  const days = Math.floor(seconds / DAY)
  const hours = Math.round((seconds % DAY) / HOUR)
  return hours > 0 && days < 10 ? `${days}d ${hours}h` : `${days}d`
}

/** The compact form used inside the timeline, where space is tight. */
export function formatDurationShort(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < HOUR) return `${Math.max(1, Math.round(seconds / MINUTE))}m`
  if (seconds < DAY) return `${Math.round(seconds / HOUR)}h`
  return `${(seconds / DAY).toFixed(seconds < 10 * DAY ? 1 : 0)}d`
}

export function formatMetricValue(metric: Metric): string {
  if (metric.value === null) return '—'

  switch (metric.unit) {
    case 'seconds':
      return formatDuration(metric.value)
    case 'ratio':
      return `${(metric.value * 100).toFixed(1)}%`
    case 'per_day':
      return metric.value >= 1
        ? `${metric.value.toFixed(1)}`
        : `${(metric.value * 7).toFixed(1)}`
    default:
      return String(metric.value)
  }
}

/** The unit caption that sits under a metric value. */
export function formatMetricUnit(metric: Metric): string {
  if (metric.value === null) return 'no data in this window'
  switch (metric.unit) {
    case 'per_day':
      return metric.value >= 1 ? 'per day' : 'per week'
    case 'ratio':
      return 'of deployments'
    case 'seconds':
      return 'median'
    default:
      return ''
  }
}

export function formatTrend(trend: number | null): string {
  if (trend === null) return 'no prior window'
  if (Math.abs(trend) < 0.01) return 'flat'
  return `${trend > 0 ? '+' : ''}${(trend * 100).toFixed(0)}%`
}

/**
 * Whether a trend is good news. Only deployment frequency improves by rising;
 * every other metric improves by falling.
 */
export function trendSentiment(metric: Metric): 'good' | 'bad' | 'neutral' {
  if (metric.trend === null || Math.abs(metric.trend) < 0.01) return 'neutral'
  const rising = metric.trend > 0
  return rising === metric.higher_is_better ? 'good' : 'bad'
}

export const BAND_LABEL: Record<Band, string> = {
  elite: 'Elite',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Critical',
  elevated: 'Elevated',
  healthy: 'Healthy',
}

export function formatCount(value: number, singular: string, plural = `${singular}s`): string {
  return `${value.toLocaleString()} ${value === 1 ? singular : plural}`
}

export function formatRelativeTime(iso: string | null): string {
  if (!iso) return 'never'
  const delta = (Date.now() - new Date(iso).getTime()) / 1000
  if (delta < MINUTE) return 'just now'
  if (delta < HOUR) return `${Math.round(delta / MINUTE)}m ago`
  if (delta < DAY) return `${Math.round(delta / HOUR)}h ago`
  return `${Math.round(delta / DAY)}d ago`
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function formatPercent(value: number | null, digits = 0): string {
  return value === null ? '—' : `${(value * 100).toFixed(digits)}%`
}
