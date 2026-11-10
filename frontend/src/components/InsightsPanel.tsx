import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'

import { formatRelativeTime } from '@/lib/format'
import type { Insight } from '@/lib/types'
import './InsightsPanel.css'

interface Props {
  insight: Insight | null
  isGenerating: boolean
  error: string | null
  llmConfigured: boolean
  onGenerate: () => void
}

export function InsightsPanel({
  insight,
  isGenerating,
  error,
  llmConfigured,
  onGenerate,
}: Props) {
  const reduceMotion = useReducedMotion()

  return (
    <section className="insights" aria-labelledby="insights-heading">
      <header className="insights__header">
        <div>
          <h2 id="insights-heading" className="insights__title">
            Recommendations
          </h2>
          <p className="insights__subtitle">
            {insight
              ? `Generated ${formatRelativeTime(insight.created_at)} by ${insight.model}`
              : 'Reads the stage percentiles and proposes where to spend effort.'}
          </p>
        </div>

        <button
          type="button"
          className="insights__action"
          onClick={onGenerate}
          disabled={isGenerating || !llmConfigured}
        >
          {isGenerating ? 'Analyzing…' : insight ? 'Analyze again' : 'Analyze delivery'}
        </button>
      </header>

      {!llmConfigured && (
        <p className="insights__notice">
          Recommendations need an OpenRouter key. Start the API with
          <code> scripts/dev.sh </code>
          to load it from your vault.
        </p>
      )}

      {error && (
        <p className="insights__notice" data-tone="error" role="alert">
          {error}
        </p>
      )}

      <AnimatePresence mode="wait">
        {isGenerating && !insight && (
          <motion.div
            key="loading"
            className="insights__loading"
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            {/* Something appears immediately, and the wording says what is happening. */}
            <p>Reading stage percentiles, CI health and the trend against the prior window…</p>
          </motion.div>
        )}

        {insight && (
          <motion.div
            key={insight.id}
            initial={reduceMotion ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.32, 0.72, 0, 1] }}
          >
            <p className="insights__headline">{insight.headline}</p>
            <p className="insights__summary">{insight.summary}</p>

            <ol className="insights__list">
              {insight.recommendations.map((recommendation, index) => (
                <li key={recommendation.title} className="recommendation">
                  <span className="recommendation__rank" aria-hidden="true">
                    {index + 1}
                  </span>

                  <div className="recommendation__body">
                    <h3 className="recommendation__title">{recommendation.title}</h3>

                    <p className="recommendation__meta">
                      <span data-impact={recommendation.impact}>
                        {recommendation.impact} impact
                      </span>
                      <span aria-hidden="true">·</span>
                      <span>{recommendation.effort} effort</span>
                      <span aria-hidden="true">·</span>
                      <span>{recommendation.stage}</span>
                    </p>

                    <p className="recommendation__rationale">{recommendation.rationale}</p>
                    <p className="recommendation__effect">{recommendation.expected_effect}</p>

                    {recommendation.ai_note && (
                      <p
                        className="recommendation__ai"
                        data-applies={recommendation.ai_assisted}
                      >
                        <span className="recommendation__ai-label">
                          {recommendation.ai_assisted
                            ? 'Assisted workflow'
                            : 'Not a model problem'}
                        </span>
                        {recommendation.ai_note}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ol>

            {insight.risks.length > 0 && (
              <div className="insights__risks">
                <h3 className="insights__risks-title">Read these numbers carefully</h3>
                <ul>
                  {insight.risks.map((risk) => (
                    <li key={risk}>{risk}</li>
                  ))}
                </ul>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {!insight && !isGenerating && llmConfigured && !error && (
        <p className="insights__empty">
          Nothing analyzed yet for this window. Run an analysis to get a ranked set of changes.
        </p>
      )}
    </section>
  )
}
