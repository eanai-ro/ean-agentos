# :rocket: CI/CD Pipeline — Multi-Agent Design

> Real output from a live multi-agent orchestration session.

**Prompt:** "Design a CI/CD pipeline for a Node.js microservice deploying to Kubernetes. Must include testing, security scanning, and zero-downtime deployment."

---

## Agent Outputs

### Gemini — DevOps Engineer

```
ROLE: DevOps Engineer

PIPELINE DESIGN (GitHub Actions):

Stage 1: CI Tests
  - Checkout code
  - Install dependencies (npm ci)
  - Run linter (eslint)
  - Run unit tests (vitest --coverage)
  - Run integration tests (testcontainers)
  - Upload coverage report
  Trigger: Every push and PR

Stage 2: Docker Build
  - Build multi-stage Docker image
  - Tag with git SHA and semantic version
  - Push to container registry (ECR/GCR)

Stage 3: Security Scan
  - Trivy scan on Docker image (CRITICAL/HIGH)
  - npm audit for dependency vulnerabilities
  - Fail pipeline if CRITICAL findings

Stage 4: Deploy to Staging
  - Apply Kubernetes manifests to staging namespace
  - Run smoke tests against staging URL
  - Run E2E tests (Playwright)
  - Wait for manual approval

Stage 5: Deploy to Production
  - Rolling update in production namespace
  - Health check with readiness probe
  - Automatic rollback if health check fails

YAML SNIPPET:
  deploy-production:
    needs: [staging-approval]
    steps:
      - kubectl set image deployment/app app=$IMAGE
      - kubectl rollout status deployment/app --timeout=300s
      - if [ $? -ne 0 ]; then kubectl rollout undo deployment/app; fi
```

### Kimi — DevOps Engineer

```
ROLE: DevOps Engineer

PIPELINE DESIGN (GitLab CI / GitHub Actions):

Stage 1: Test + Lint
  - npm ci --frozen-lockfile
  - eslint . --max-warnings 0
  - vitest run --coverage --min-coverage 80
  - TypeScript strict compile check (tsc --noEmit)
  Gate: Coverage >= 80%, zero lint warnings

Stage 2: Build + Scan
  - Docker build (multi-stage, distroless base)
  - Trivy image scan (fail on CRITICAL)
  - Snyk test for dependency vulnerabilities
  - SBOM generation (syft)
  Gate: Zero CRITICAL vulnerabilities

Stage 3: Push + Tag
  - Push image to registry with tags:
    - :latest (for staging)
    - :v1.2.3 (semantic version)
    - :sha-abc123 (commit SHA)
  - Update Helm chart values

Stage 4: Staging Deploy
  - Helm upgrade --install to staging
  - Wait for all pods ready
  - Run integration test suite against staging
  - Performance baseline test (k6, 100 VU, 60s)
  Gate: All tests pass, p99 latency < 200ms

Stage 5: Production Deploy (Canary)
  - Deploy canary (10% traffic)
  - Monitor error rate and latency for 10 minutes
  - If error rate < 0.1%: promote to 50% → 100%
  - If error rate > 1%: automatic rollback
  - Post-deploy: tag release in Git, notify Slack

CANARY CONFIG:
  strategy:
    canary:
      steps:
        - setWeight: 10
        - pause: {duration: 10m}
        - setWeight: 50
        - pause: {duration: 5m}
        - setWeight: 100
      analysis:
        metrics:
          - name: error-rate
            threshold: 1
            provider: prometheus
```

### Codex — DevOps Engineer

```
ROLE: DevOps Engineer

PIPELINE DESIGN:

Stage 1: Test
  - Install: npm ci
  - Lint: eslint + prettier --check
  - Unit tests: vitest (parallel, with coverage)
  - Type check: tsc --noEmit
  - Gate: 80% coverage, zero errors

Stage 2: Build
  - Docker multi-stage build:
    FROM node:20-slim AS builder
    FROM gcr.io/distroless/nodejs20-debian12
  - Layer caching for node_modules
  - Image size target: < 150MB
  - Tag: registry/app:sha-${GITHUB_SHA::7}

Stage 3: Security Scan
  - Trivy: scan image for OS + library CVEs
  - npm audit: --audit-level=high
  - Gitleaks: scan for hardcoded secrets
  - Gate: No CRITICAL CVEs, no secrets detected

Stage 4: Staging Deploy
  - kubectl apply to staging namespace
  - Wait: kubectl rollout status (timeout 5m)
  - Smoke tests: health endpoint + critical paths
  - Integration tests: API contract validation
  - Manual approval gate for production

Stage 5: Production Deploy
  - Rolling update: maxSurge 1, maxUnavailable 0
  - Readiness probe must pass before traffic routes
  - Liveness probe for ongoing health
  - Automatic rollback on failed rollout:

  kubectl rollout status deployment/app --timeout=300s || \
    kubectl rollout undo deployment/app

  Post-deploy:
  - Verify metrics in Grafana (5-minute window)
  - Create GitHub release with changelog
  - Notify team via Slack webhook
```

---

## Synthesis

### Pipeline Consensus

All three agents designed a 5-stage pipeline with the same core structure:

```
TEST → BUILD → SCAN → STAGING → PRODUCTION
```

### Comparison Matrix

| Feature | Gemini | Kimi | Codex |
|---------|--------|------|-------|
| Test coverage gate | Yes | 80% min | 80% min |
| Docker base | multi-stage | distroless | distroless |
| Security scanner | Trivy | Trivy + Snyk | Trivy + Gitleaks |
| Staging tests | smoke + E2E | integration + perf | smoke + contract |
| Production strategy | rolling update | canary (10→50→100%) | rolling update |
| Rollback | manual kubectl | automatic on metrics | automatic on status |
| SBOM generation | No | Yes (syft) | No |
| Performance testing | No | Yes (k6) | No |

### Recommended Combined Pipeline

```yaml
stages:
  test:       lint + type-check + unit tests (80% coverage gate)
  build:      multi-stage Docker, distroless base, < 150MB
  scan:       Trivy + npm audit + Gitleaks (fail on CRITICAL)
  staging:    Helm deploy + smoke + integration + k6 baseline
  production: Canary 10%→50%→100% with Prometheus metrics gate
              Auto-rollback if error rate > 1% or p99 > 500ms
```

---

> Multi-agent orchestration is a Pro feature. Contact: ean@eanai.ro
