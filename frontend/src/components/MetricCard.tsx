import { Sparkline } from '@/charts/Sparkline'
import {
  BAND_LABEL,
  formatDuration,
  formatMetricUnit,
  formatMetricValue,
  formatTrend,
  trendSentiment,
} from '@/lib/format'
import type { Metric } from '@/lib/types'
import './MetricCard.css'

interface Props {
  metric: Metric
}

/** Shapes a raw series value for the sparkline readout, per metric unit. */
function valueFormatter(metric: Metric): (value: number) => string {
  switch (metric.unit) {
    case 'seconds':
      return formatDuration
    case 'ratio':
      return (value) => `${(value * 100).toFixed(1)}%`
    default:
      return (value) => `${value.toFixed(1)} deploys`
  }
}

export function MetricCard({ metric }: Props) {
  const sentiment = trendSentiment(metric)
  const hasData = metric.value !== null

  return (
    <article className="metric" aria-labelledby={`metric-${metric.key}`}>
      <header className="metric__header">
        <h3 id={`metric-${metric.key}`} className="metric__label">
          {metric.label}
        </h3>
        {metric.band && (
          <span className="metric__band" data-band={metric.band}>
            {BAND_LABEL[metric.band]}
          </span>
        )}
      </header>

      <p className="metric__value" data-numeric>
        {formatMetricValue(metric)}
      </p>
      <p className="metric__unit">{formatMetricUnit(metric)}</p>

      {hasData && (
        <p className="metric__trend" data-sentiment={sentiment}>
          {/* The arrow states direction; the word states whether that is good,
              so meaning never rests on colour alone. */}
          <span aria-hidden="true">
            {metric.trend === null ? '·' : metric.trend > 0 ? '↑' : '↓'}
          </span>
          <span>{formatTrend(metric.trend)}</span>
          <span className="metric__trend-context">
            vs previous {metric.sample_count > 0 ? 'window' : 'window'}
            {sentiment !== 'neutral' && (
              <span className="visually-hidden">
                , which is {sentiment === 'good' ? 'an improvement' : 'a regression'}
              </span>
            )}
          </span>
        </p>
      )}

      {metric.series.length > 1 && (
        <Sparkline
          points={metric.series}
          format={valueFormatter(metric)}
          label={metric.label}
        />
      )}

      <footer className="metric__footer">
        {metric.sample_count === 0
          ? 'No events recorded in this window'
          : `${metric.sample_count.toLocaleString()} events`}
      </footer>
    </article>
  )
}
