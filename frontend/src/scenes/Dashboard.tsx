import { useState } from 'react'

import { LifecycleTrack } from '@/charts/LifecycleTrack'
import { BottleneckList } from '@/components/BottleneckList'
import { InsightsPanel } from '@/components/InsightsPanel'
import { MetricCard } from '@/components/MetricCard'
import { PullRequestTable } from '@/components/PullRequestTable'
import { formatCount, formatDuration, formatPercent } from '@/lib/format'
import type { Insight, PullRequestRow, Snapshot, Stage } from '@/lib/types'
import './Dashboard.css'

interface Props {
  snapshot: Snapshot
  pullRequests: PullRequestRow[]
  insight: Insight | null
  isGenerating: boolean
  insightError: string | null
  llmConfigured: boolean
  onGenerate: () => void
}

export function Dashboard({
  snapshot,
  pullRequests,
  insight,
  isGenerating,
  insightError,
  llmConfigured,
  onGenerate,
}: Props) {
  const [selectedStage, setSelectedStage] = useState<Stage | null>(null)
  const { ci } = snapshot

  return (
    <div className="dashboard shell">
      <section className="dashboard__section" aria-labelledby="pipeline-heading">
        <div className="dashboard__section-head">
          <h2 id="pipeline-heading" className="dashboard__heading">
            Inspect a stage
          </h2>
          <p className="dashboard__caption">
            {formatCount(snapshot.pull_request_count, 'pull request')} from{' '}
            {formatCount(snapshot.contributor_count, 'contributor')} over {snapshot.window_days}{' '}
            days. Select a segment for its spread, from the median to the slowest tenth.
          </p>
        </div>

        <LifecycleTrack
          stages={snapshot.stages}
          onSelect={(stage) =>
            setSelectedStage((current) => (current?.stage === stage.stage ? null : stage))
          }
          selectedStage={selectedStage?.stage ?? null}
        />

        {selectedStage && (
          <dl className="dashboard__stage-detail">
            <div>
              <dt>Median</dt>
              <dd data-numeric>{formatDuration(selectedStage.p50_seconds)}</dd>
            </div>
            <div>
              <dt>Upper quartile</dt>
              <dd data-numeric>{formatDuration(selectedStage.p75_seconds)}</dd>
            </div>
            <div>
              <dt>Slowest tenth</dt>
              <dd data-numeric>{formatDuration(selectedStage.p90_seconds)}</dd>
            </div>
            <div>
              <dt>Share of pipeline</dt>
              <dd data-numeric>{formatPercent(selectedStage.share_of_pipeline)}</dd>
            </div>
          </dl>
        )}
      </section>

      <section className="dashboard__section" aria-labelledby="dora-heading">
        <div className="dashboard__section-head">
          <h2 id="dora-heading" className="dashboard__heading">
            Delivery performance
          </h2>
          <p className="dashboard__caption">
            The four DORA measures, each banded against the published cutoffs.
          </p>
        </div>

        <div className="dashboard__metrics">
          {snapshot.metrics.map((metric) => (
            <MetricCard key={metric.key} metric={metric} />
          ))}
        </div>
      </section>

      <section className="dashboard__section" aria-labelledby="bottleneck-heading">
        <div className="dashboard__section-head">
          <h2 id="bottleneck-heading" className="dashboard__heading">
            Worth fixing first
          </h2>
          <p className="dashboard__caption">
            Ranked by how far past target each stage sits. Queues outrank active work, because
            removing a wait costs no engineering time.
          </p>
        </div>
        <BottleneckList bottlenecks={snapshot.bottlenecks} />
      </section>

      <section className="dashboard__section" aria-labelledby="ci-heading">
        <div className="dashboard__section-head">
          <h2 id="ci-heading" className="dashboard__heading">
            Continuous integration
          </h2>
          <p className="dashboard__caption">
            Slow or flaky pipelines push time into every stage downstream.
          </p>
        </div>

        <dl className="dashboard__ci">
          <div>
            <dt>Median run</dt>
            <dd data-numeric>{formatDuration(ci.median_duration_seconds)}</dd>
          </div>
          <div>
            <dt>Slowest tenth</dt>
            <dd data-numeric>{formatDuration(ci.p90_duration_seconds)}</dd>
          </div>
          <div>
            <dt>First-attempt pass rate</dt>
            <dd data-numeric>{formatPercent(ci.success_rate, 1)}</dd>
          </div>
          <div>
            <dt>Passed only on retry</dt>
            <dd data-numeric>{formatPercent(ci.flake_rate, 1)}</dd>
          </div>
          <div>
            <dt>Runs analyzed</dt>
            <dd data-numeric>{ci.total_runs.toLocaleString()}</dd>
          </div>
          <div>
            <dt>Median change size</dt>
            <dd data-numeric>
              {snapshot.median_pr_size === null
                ? '—'
                : `${Math.round(snapshot.median_pr_size).toLocaleString()} lines`}
            </dd>
          </div>
        </dl>
      </section>

      <InsightsPanel
        insight={insight}
        isGenerating={isGenerating}
        error={insightError}
        llmConfigured={llmConfigured}
        onGenerate={onGenerate}
      />

      <section className="dashboard__section" aria-labelledby="prs-heading">
        <div className="dashboard__section-head">
          <h2 id="prs-heading" className="dashboard__heading">
            Pull requests
          </h2>
          <p className="dashboard__caption">
            Every change in the window, with the same stage encoding at row scale.
          </p>
        </div>
        <PullRequestTable rows={pullRequests} />
      </section>
    </div>
  )
}
