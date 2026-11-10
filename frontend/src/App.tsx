import { useEffect, useRef, useState } from 'react'

import { Header } from '@/components/Header'
import {
  errorMessage,
  useGenerateInsight,
  useHealth,
  useInsight,
  usePullRequests,
  useRepositories,
  useSnapshot,
} from '@/hooks/useDelivery'
import { useSlowRequest } from '@/hooks/useSlowRequest'
import { Dashboard } from '@/scenes/Dashboard'
import { Hero } from '@/scenes/Hero'
import './App.css'

export default function App() {
  const mainRef = useRef<HTMLElement>(null)
  const [repositoryId, setRepositoryId] = useState<number | null>(null)
  const [windowDays, setWindowDays] = useState(30)

  const health = useHealth()
  const repositories = useRepositories()
  const snapshot = useSnapshot(repositoryId, windowDays)
  const pullRequests = usePullRequests(repositoryId, windowDays)
  const insight = useInsight(repositoryId)
  const generate = useGenerateInsight(repositoryId, windowDays)

  // Land on the first repository until someone picks another.
  useEffect(() => {
    if (repositoryId === null && repositories.data?.length) {
      setRepositoryId(repositories.data[0]!.id)
    }
  }, [repositories.data, repositoryId])

  const connectionError = errorMessage(repositories.error ?? snapshot.error)
  const wakingUp = useSlowRequest(!snapshot.data && !connectionError)

  if (connectionError) {
    return (
      <main className="state">
        <div className="shell state__inner">
          <h1 className="state__title">The dashboard cannot reach the API.</h1>
          <p className="state__body">{connectionError}</p>
          <p className="state__hint">
            Start the service with <code>make dev</code>, then reload this page.
          </p>
        </div>
      </main>
    )
  }

  if (!snapshot.data) {
    return (
      <main className="state" aria-busy="true">
        <div className="shell state__inner">
          <p className="state__loading">Loading delivery data…</p>
          {wakingUp && (
            <p className="state__hint">
              The API sleeps when idle, so the first request after a quiet spell takes about a
              minute to wake it. Later ones are immediate.
            </p>
          )}
        </div>
      </main>
    )
  }

  return (
    <>
      <a href="#main" className="skip-link">
        Skip to dashboard
      </a>

      <Header
        repositories={repositories.data ?? []}
        selectedId={repositoryId}
        onSelect={setRepositoryId}
        windowDays={windowDays}
        onWindowChange={setWindowDays}
      />

      <Hero
        stages={snapshot.data.stages}
        repositoryName={snapshot.data.repository.full_name}
        onEnter={() => mainRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
      />

      <main id="main" ref={mainRef}>
        <Dashboard
          snapshot={snapshot.data}
          pullRequests={pullRequests.data ?? []}
          insight={insight.data ?? null}
          isGenerating={generate.isPending}
          insightError={errorMessage(generate.error)}
          llmConfigured={health.data?.llm_configured ?? false}
          onGenerate={() => generate.mutate()}
        />
      </main>

      <footer className="footer">
        <div className="shell footer__inner">
          <span>DevPulse</span>
          <span>
            {snapshot.data.repository.full_name} · {windowDays}-day window
          </span>
        </div>
      </footer>
    </>
  )
}
