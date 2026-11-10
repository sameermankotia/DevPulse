import { useMemo, useState } from 'react'

import { formatDuration } from '@/lib/format'
import type { PullRequestRow, StageKey } from '@/lib/types'
import './PullRequestTable.css'

interface Props {
  rows: PullRequestRow[]
}

type SortKey = 'number' | 'lead_time' | 'size'

const STAGE_ORDER: StageKey[] = ['code', 'pickup', 'review', 'rework', 'release']
const QUEUE_STAGES = new Set<StageKey>(['pickup', 'rework', 'release'])

/**
 * Per-pull-request detail. The inline bar repeats the lifecycle track at row
 * scale, so the same shape means the same thing everywhere in the product.
 */
export function PullRequestTable({ rows }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('lead_time')

  const sorted = useMemo(() => {
    const copy = [...rows]
    copy.sort((a, b) => {
      switch (sortKey) {
        case 'lead_time':
          return (b.lead_time_seconds ?? -1) - (a.lead_time_seconds ?? -1)
        case 'size':
          return b.additions + b.deletions - (a.additions + a.deletions)
        default:
          return b.number - a.number
      }
    })
    return copy
  }, [rows, sortKey])

  if (rows.length === 0) {
    return <p className="prs__empty">No pull requests opened in this window.</p>
  }

  return (
    <div className="prs">
      <div className="prs__controls">
        <label htmlFor="pr-sort" className="prs__sort-label">
          Sort by
        </label>
        <select
          id="pr-sort"
          className="prs__sort"
          value={sortKey}
          onChange={(event) => setSortKey(event.target.value as SortKey)}
        >
          <option value="lead_time">Slowest first</option>
          <option value="size">Largest first</option>
          <option value="number">Newest first</option>
        </select>
      </div>

      <table className="prs__table">
        <caption className="visually-hidden">
          Pull requests in this window with their lifecycle stage breakdown.
        </caption>
        <thead>
          <tr>
            <th scope="col">Pull request</th>
            <th scope="col">Author</th>
            <th scope="col" className="prs__numeric">
              Size
            </th>
            <th scope="col" className="prs__numeric">
              Lead time
            </th>
            <th scope="col" className="prs__breakdown-head">
              Where the time went
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const total = STAGE_ORDER.reduce((sum, stage) => sum + (row.stages[stage] ?? 0), 0)

            return (
              <tr key={row.number}>
                <th scope="row" className="prs__title">
                  <span className="prs__number">#{row.number}</span>
                  <span className="prs__headline">{row.title}</span>
                </th>
                <td className="prs__author">{row.author}</td>
                <td className="prs__numeric" data-numeric>
                  {(row.additions + row.deletions).toLocaleString()}
                </td>
                <td className="prs__numeric" data-numeric>
                  {formatDuration(row.lead_time_seconds)}
                </td>
                <td>
                  {total > 0 ? (
                    <span className="prs__bar">
                      {STAGE_ORDER.map((stage) => {
                        const seconds = row.stages[stage]
                        if (!seconds) return null
                        return (
                          <span
                            key={stage}
                            className="prs__segment"
                            data-queue={QUEUE_STAGES.has(stage)}
                            style={{ flexGrow: seconds }}
                            title={`${stage}: ${formatDuration(seconds)}`}
                          />
                        )
                      })}
                    </span>
                  ) : (
                    <span className="prs__pending">Still in flight</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
