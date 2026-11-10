import { useId, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'

import { formatDuration, formatDurationShort } from '@/lib/format'
import type { Stage } from '@/lib/types'
import './LifecycleTrack.css'

interface Props {
  stages: Stage[]
  /** 0-1. Drives the reveal when the track is used as a scroll scene. */
  progress?: number
  /** Shows the per-stage caption row. Off in compact contexts. */
  showLabels?: boolean
  onSelect?: (stage: Stage) => void
  selectedStage?: string | null
}

/**
 * The lifecycle track.
 *
 * Each segment's width is its share of median pipeline time, so a stage that
 * takes four days is literally four times wider than one that takes a day.
 * Queue stages -- where nobody is working and the change is just waiting --
 * are hatched rather than solid, so the distinction survives greyscale and
 * colour blindness.
 */
export function LifecycleTrack({
  stages,
  progress = 1,
  showLabels = true,
  onSelect,
  selectedStage,
}: Props) {
  const hatchId = useId()
  const reduceMotion = useReducedMotion()
  const [hovered, setHovered] = useState<string | null>(null)

  const measured = stages.filter(
    (stage) => stage.p50_seconds !== null && stage.sample_count > 0,
  )
  const total = measured.reduce((sum, stage) => sum + (stage.p50_seconds ?? 0), 0)

  if (total === 0) {
    return (
      <p className="track__empty">
        No completed pull requests in this window, so there is no pipeline to measure yet.
      </p>
    )
  }

  // Segments narrower than this cannot hold a label or be comfortably clicked.
  const MIN_SHARE = 0.035
  const widths = measured.map((stage) => Math.max((stage.p50_seconds ?? 0) / total, MIN_SHARE))
  const widthTotal = widths.reduce((sum, width) => sum + width, 0)

  let cursor = 0
  const segments = measured.map((stage, index) => {
    const share = (widths[index] ?? 0) / widthTotal
    const segment = { stage, share, offset: cursor }
    cursor += share
    return segment
  })

  const active = hovered ?? selectedStage ?? null

  return (
    <div className="track">
      <svg
        className="track__canvas"
        viewBox="0 0 1000 56"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Pipeline time by stage. ${measured
          .map((s) => `${s.label}, ${formatDuration(s.p50_seconds)}`)
          .join('. ')}.`}
      >
        <defs>
          {/* Queue stages are hatched so waiting is distinguishable without colour. */}
          <pattern
            id={hatchId}
            width="8"
            height="8"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <rect width="8" height="8" fill="var(--friction-wash)" />
            <line x1="0" y1="0" x2="0" y2="8" stroke="var(--friction)" strokeWidth="3" />
          </pattern>
        </defs>

        {segments.map(({ stage, share, offset }) => {
          const x = offset * 1000
          const width = share * 1000
          const revealed = Math.min(Math.max((progress - offset) / share, 0), 1)
          const isActive = active === stage.stage

          return (
            <g key={stage.stage}>
              {/* The outline is always laid out, so the widths -- which are the
                  data -- are honest before any scrolling happens. The fill is
                  what the scroll scrubs in. */}
              <rect
                x={x}
                y={0}
                width={Math.max(width - 2, 1)}
                height={56}
                rx={4}
                fill="none"
                stroke={stage.is_queue ? 'var(--friction)' : 'var(--flow)'}
                strokeWidth={1}
                opacity={isActive || active === null ? 0.45 : 0.18}
              />
              <rect
                x={x}
                y={0}
                width={Math.max(width - 2, 1)}
                height={56}
                rx={4}
                fill={stage.is_queue ? `url(#${hatchId})` : 'var(--flow)'}
                opacity={isActive || active === null ? 1 : 0.32}
                style={{
                  transform: `scaleX(${reduceMotion ? 1 : revealed})`,
                  transformOrigin: `${x}px center`,
                  transition: 'opacity var(--duration-base) var(--ease-standard)',
                }}
              />
            </g>
          )
        })}
      </svg>

      {/* Interactive overlay: real buttons, so the track is keyboard operable. */}
      <div className="track__hits">
        {segments.map(({ stage, share }) => (
          <button
            key={stage.stage}
            type="button"
            className="track__hit"
            style={{ flexBasis: `${share * 100}%` }}
            aria-pressed={selectedStage === stage.stage}
            onMouseEnter={() => setHovered(stage.stage)}
            onMouseLeave={() => setHovered(null)}
            onFocus={() => setHovered(stage.stage)}
            onBlur={() => setHovered(null)}
            onClick={() => onSelect?.(stage)}
          >
            <span className="visually-hidden">
              {stage.label}: {formatDuration(stage.p50_seconds)} median,{' '}
              {stage.is_queue ? 'waiting' : 'active work'}, from {stage.sample_count} pull
              requests.
            </span>
          </button>
        ))}
      </div>

      {showLabels && (
        <ul className="track__legend">
          {segments.map(({ stage, share }) => (
            <li
              key={stage.stage}
              className="track__legend-item"
              data-queue={stage.is_queue}
              data-active={active === stage.stage}
              style={{ flexBasis: `${share * 100}%` }}
            >
              <span className="track__legend-duration">
                {formatDurationShort(stage.p50_seconds)}
              </span>
              <span className="track__legend-label">{stage.label}</span>
            </li>
          ))}
        </ul>
      )}

      {active && (
        <motion.p
          key={active}
          className="track__readout"
          initial={reduceMotion ? false : { opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.18, ease: [0.32, 0.72, 0, 1] }}
        >
          {measured.find((s) => s.stage === active)?.description}
        </motion.p>
      )}
    </div>
  )
}
