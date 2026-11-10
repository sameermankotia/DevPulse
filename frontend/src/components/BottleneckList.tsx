import { formatDuration, formatPercent } from '@/lib/format'
import type { Bottleneck } from '@/lib/types'
import './BottleneckList.css'

interface Props {
  bottlenecks: Bottleneck[]
}

export function BottleneckList({ bottlenecks }: Props) {
  if (bottlenecks.length === 0) {
    return (
      <div className="bottlenecks__clear">
        <p className="bottlenecks__clear-title">Every stage is inside its target.</p>
        <p className="bottlenecks__clear-body">
          Nothing in this window is queueing long enough to be worth attacking. Widen the window
          to look for slower-moving drift.
        </p>
      </div>
    )
  }

  return (
    <ol className="bottlenecks">
      {bottlenecks.map((bottleneck) => (
        <li key={bottleneck.stage} className="bottleneck" data-severity={bottleneck.severity}>
          <div className="bottleneck__head">
            <h3 className="bottleneck__title">{bottleneck.label}</h3>
            <span className="bottleneck__tag">
              {bottleneck.is_queue ? 'Queue' : 'Active work'}
            </span>
          </div>

          <p className="bottleneck__figure" data-numeric>
            {formatDuration(bottleneck.p50_seconds)}
            <span className="bottleneck__figure-unit">median</span>
          </p>

          <dl className="bottleneck__facts">
            <div>
              <dt>Target</dt>
              <dd data-numeric>{formatDuration(bottleneck.threshold_seconds)}</dd>
            </div>
            <div>
              <dt>Slowest tenth</dt>
              <dd data-numeric>{formatDuration(bottleneck.p90_seconds)}</dd>
            </div>
            <div>
              <dt>Share of pipeline</dt>
              <dd data-numeric>{formatPercent(bottleneck.share_of_pipeline)}</dd>
            </div>
            <div>
              <dt>Sampled from</dt>
              <dd data-numeric>{bottleneck.sample_count} PRs</dd>
            </div>
          </dl>

          <p className="bottleneck__evidence">
            {bottleneck.overage.toFixed(1)}× over target.
            {bottleneck.evidence_pr_numbers.length > 0 && (
              <>
                {' '}
                Worst offenders:{' '}
                {bottleneck.evidence_pr_numbers.map((number) => `#${number}`).join(', ')}.
              </>
            )}
          </p>
        </li>
      ))}
    </ol>
  )
}
