import { useRef, useState } from 'react'
import {
  motion,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useTransform,
} from 'framer-motion'

import { LifecycleTrack } from '@/charts/LifecycleTrack'
import { formatDuration } from '@/lib/format'
import type { Stage } from '@/lib/types'
import './Hero.css'

interface Props {
  stages: Stage[]
  repositoryName: string
  onEnter: () => void
}

/**
 * The scroll scene.
 *
 * One orchestrated moment for the whole product: the pipeline draws itself
 * across the viewport as you scroll, then the waiting separates from the work.
 * Everything after this responds to the user rather than playing on its own.
 */
export function Hero({ stages, repositoryName, onEnter }: Props) {
  const sceneRef = useRef<HTMLDivElement>(null)
  const reduceMotion = useReducedMotion()
  const [drawn, setDrawn] = useState(0)

  const { scrollYProgress } = useScroll({
    target: sceneRef,
    offset: ['start start', 'end end'],
  })

  // The track draws across the first half; the verdict resolves after it.
  const draw = useTransform(scrollYProgress, [0.02, 0.5], [0, 1])
  const headlineOpacity = useTransform(scrollYProgress, [0, 0.14, 0.32], [1, 1, 0])
  const headlineY = useTransform(scrollYProgress, [0, 0.32], [0, -48])
  const trackScale = useTransform(scrollYProgress, [0.02, 0.5], [0.97, 1])
  const verdictOpacity = useTransform(scrollYProgress, [0.54, 0.7], [0, 1])
  const verdictY = useTransform(scrollYProgress, [0.54, 0.7], [24, 0])

  useMotionValueEvent(draw, 'change', setDrawn)

  const measured = stages.filter((s) => s.p50_seconds !== null && s.sample_count > 0)
  const sum = (queue: boolean) =>
    measured
      .filter((s) => s.is_queue === queue)
      .reduce((total, s) => total + (s.p50_seconds ?? 0), 0)

  const waiting = sum(true)
  const total = waiting + sum(false)
  const waitingPercent = total > 0 ? Math.round((waiting / total) * 100) : 0

  // Reduced motion gets the finished state, not a degraded animation.
  const progress = reduceMotion ? 1 : drawn
  const motionStyle = (style: Record<string, unknown>) => (reduceMotion ? undefined : style)

  return (
    <section className="hero" ref={sceneRef} aria-labelledby="hero-heading">
      <div className="hero__sticky">
        <div className="shell hero__inner">
          <motion.div
            className="hero__headline"
            style={motionStyle({ opacity: headlineOpacity, y: headlineY })}
          >
            <h1 id="hero-heading" className="hero__title">
              Your code spends most
              <br />
              of its life waiting.
            </h1>
            <p className="hero__lede">
              DevPulse reads every pull request, review and deployment, then lays the pipeline
              out to scale. The wide parts are where the time goes.
            </p>
          </motion.div>

          <motion.div className="hero__track" style={motionStyle({ scale: trackScale })}>
            <p className="hero__track-caption">
              {repositoryName} · median pull request · last 30 days
            </p>
            <LifecycleTrack stages={stages} progress={progress} />
          </motion.div>

          <motion.div
            className="hero__verdict"
            style={motionStyle({ opacity: verdictOpacity, y: verdictY })}
          >
            <p className="hero__verdict-line">
              <span className="hero__verdict-figure" data-numeric>
                {formatDuration(waiting)}
              </span>
              <span>
                of the {formatDuration(total)} median is queue time. Nobody is working on the
                change — it is waiting its turn.
              </span>
            </p>
            <button type="button" className="hero__cta" onClick={onEnter}>
              See the breakdown
            </button>
          </motion.div>
        </div>
      </div>

      {/* The conclusion in text, for screen readers and anyone who skips the scene. */}
      <p className="visually-hidden">
        {waitingPercent} percent of median pipeline time is spent waiting in a queue rather than
        in active work.
      </p>
    </section>
  )
}
