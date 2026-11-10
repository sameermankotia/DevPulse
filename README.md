# DevPulse

Developer Productivity Intelligence Platform.

DevPulse reads pull request, review and CI/CD data from GitHub, reconstructs the
lifecycle of every change, and shows where delivery time is actually being lost.
It reports the four DORA metrics, ranks stage-level bottlenecks, and generates
recommendations — including an honest read on where AI-assisted workflows help
and where they do not.

## The idea

A pull request's life is a sequence of stages, each bounded by two timestamps:

| Stage | From | To | Queue? |
|---|---|---|---|
| Coding | first commit | pull request opened | no |
| Waiting for review | ready for review | first review | **yes** |
| In review | first review | approved | no |
| Approved, not merged | approved | merged | **yes** |
| Merged, not shipped | merged | production deploy | **yes** |

In most organisations the queue stages dominate. That matters because removing a
wait costs no engineering effort, so DevPulse ranks queue bottlenecks ahead of
work bottlenecks when their overage is comparable.

A stage is only measured when both of its boundaries exist. A missing boundary
means "not observed", never zero — counting an unreviewed pull request as zero
pickup time would drag the median down and hide the problem.

## Stack

- **Backend** — Python 3.11+, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL
- **Frontend** — React 18, TypeScript, Vite, TanStack Query, Framer Motion, hand-rolled SVG charts
- **Recommendations** — OpenRouter (`anthropic/claude-opus-4.8` by default)
- **Deployment** — Docker Compose for local, Kubernetes manifests in `deploy/k8s`

## Quick start

```bash
make install     # virtualenv + npm install

make dev         # terminal 1: API on :8000
make web         # terminal 2: frontend on :5173
```

Then open http://localhost:5173.

No database server is needed. `make dev` runs on a local SQLite file and leaves
`DEMO_MODE=true`, which seeds four repositories of realistic delivery data on
first boot, so there is nothing to install and no GitHub credentials to supply.

It reads `OPENROUTER_API_KEY` from 1Password if the `op` CLI is available. If it
is not, the API still starts and everything works except the recommendations,
which say the key is missing. To use Postgres instead, set
`DATABASE_URL_OVERRIDE` or fill in the `POSTGRES_*` variables.

Prefer Docker:

```bash
export OPENROUTER_API_KEY="$(op read 'op://OCR-Eval-Dashboard/dashboard-secrets/OPENROUTER_API_KEY')"
make up          # http://localhost:8080
```

## Credentials

Secrets are read from 1Password at launch by `scripts/dev.sh` and never written
to disk. Point it at a different item with `OP_ITEM`:

```bash
OP_ITEM="op://Private/devpulse" ./scripts/dev.sh
```

Without `op`, copy `.env.example` to `.env` and fill it in — `.env` is ignored
by git.

| Variable | Required | Effect when missing |
|---|---|---|
| `OPENROUTER_API_KEY` | for recommendations | Dashboard works; the Analyze button explains the key is missing |
| `GITHUB_TOKEN` | to sync real repositories | Demo dataset only |
| `POSTGRES_*` | in production | Falls back to the local defaults |

A `GITHUB_TOKEN` needs `repo` and `actions:read`.

## Tracking a repository

```bash
curl -X POST localhost:8000/api/v1/repositories \
  -H 'Content-Type: application/json' \
  -d '{"full_name": "owner/name", "backfill_days": 120}'
```

The first sync is inline and backfills 120 days by default. After that,
`POST /api/v1/repositories/{id}/sync` queues a background refresh, and the
`devpulse-sync` CronJob runs hourly in Kubernetes.

## API

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/v1/health` | Service, database and credential state |
| `GET` | `/api/v1/repositories` | Tracked repositories |
| `POST` | `/api/v1/repositories` | Track a repository and sync it |
| `POST` | `/api/v1/repositories/{id}/sync` | Queue a background refresh |
| `GET` | `/api/v1/repositories/{id}/snapshot` | DORA metrics, stages, bottlenecks, CI health |
| `GET` | `/api/v1/repositories/{id}/pull-requests` | Per-PR stage breakdowns |
| `GET` | `/api/v1/repositories/{id}/insights` | Most recent recommendations |
| `POST` | `/api/v1/repositories/{id}/insights` | Generate recommendations |

All windowed endpoints take `window_days` between 7 and 180 (default 30).
Interactive docs at `/docs`.

Recommendations are cached against a hash of their input digest, so an unchanged
dataset never pays to regenerate. Pass `force=true` to override.

## What the model is given

Only the numeric digest: stage percentiles, DORA values with their bands, CI
health, and trend ratios. Pull request titles, author names and repository
contents are never sent. The response is validated against a Pydantic schema,
with one repair attempt if the first reply does not parse.

## Metric definitions

Performance bands follow the published DORA cutoffs.

| Metric | Definition | Elite |
|---|---|---|
| Deployment frequency | Successful production deploys per day | ≥ 1/day |
| Lead time for changes | First commit to production deploy, median | < 1 day |
| Change failure rate | Deploys causing a failure, over all deploys | ≤ 5% |
| Time to restore | Incident opened to resolved, median | < 1 hour |

GitHub exposes no incident feed, so change failures are inferred: a merged pull
request whose title matches a revert, rollback or hotfix pattern is attributed to
the most recent production deployment that preceded it. Teams with a real
incident tracker should replace `Ingestor._derive_incidents`.

## Tests

```bash
make test     # 41 tests: statistics, stage model, DORA, API contract
make lint     # ruff + tsc
```

The API tests run against a seeded demo database, so they assert real analytics
output rather than empty-set behaviour.

## Deployment

### Free hosting: Vercel + Render

The frontend is static and the API runs on SQLite against an ephemeral disk, so
this costs nothing and nothing expires. `DEMO_MODE` re-seeds the identical
dataset from `DEMO_SEED` whenever the instance restarts, which is why the free
Postgres add-on — deleted after 30 days — is not needed.

**Render (API).** New → Blueprint, point it at this repository. `render.yaml`
defines the service. Set `OPENROUTER_API_KEY` in the dashboard when prompted;
it is marked `sync: false` so it never lives in the repository. Note the
assigned URL, e.g. `https://devpulse-api.onrender.com`.

**Vercel (frontend).** Import the repository, set **Root Directory** to
`frontend`, and add one environment variable:

```
VITE_API_BASE_URL = https://<your-render-service>.onrender.com/api/v1
```

**Close the loop.** Set `CORS_ORIGINS` on Render to the Vercel URL. Preview
deployments are already covered by `CORS_ORIGIN_REGEX`.

Calls go from the browser straight to Render rather than through Vercel, because
generating a recommendation takes longer than Vercel's edge proxy allows.

Two things to expect on the free tier: the API sleeps after 15 minutes idle, so
the first request takes roughly a minute to wake it — the UI says so rather than
appearing to hang — and because the disk is ephemeral, the recommendation cache
resets on restart.

To track real repositories instead of the demo set, add a Render Postgres
instance, remove `DATABASE_URL_OVERRIDE`, and set `DEMO_MODE=false`. The
entrypoint runs Alembic migrations whenever the database is not SQLite.

### Kubernetes

```bash
kubectl apply -f deploy/k8s/
```

Create the secret out of band rather than applying the placeholder in
`10-config.yaml`:

```bash
kubectl create secret generic devpulse-secrets -n devpulse \
  --from-literal=POSTGRES_USER=devpulse \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -base64 24)" \
  --from-literal=OPENROUTER_API_KEY="$(op read 'op://OCR-Eval-Dashboard/dashboard-secrets/OPENROUTER_API_KEY')"
```

Migrations run in an init container, so schema changes land before any new pod
serves traffic.

## Design notes

See [docs/design.md](docs/design.md) for the interface rationale: the colour
system, the proportional lifecycle track, and the accessibility constraints the
palette had to satisfy.
