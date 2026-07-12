# Spec 00d — Containerization & Deployment

**Status:** Approved
**Type:** Cross-cutting engineering spec
**Applies to:** Local development environment, deployment to Azure (or any future provider)

---

## 1. Purpose

Define how the system's services (frontend, backend, database) are packaged and run, ensuring the same setup works identically in local development and in any cloud environment, with no recurring licensing cost.

---

## 2. Decision: Docker + Docker Compose

The system is containerized using **Docker**, orchestrated locally and in simple deployments with **Docker Compose**.

**Cost:** Docker is free for this project under any scenario. Docker Desktop (the GUI application) is free for individual developers, students, and non-commercial projects — the paid tiers only apply to companies above 250 employees or $10M annual revenue, which does not apply here. The Docker Engine itself (used on Linux servers and in any cloud deployment) is open source and always free, with no licensing cost regardless of project size.

**Why Docker Compose over alternatives:**
- Kubernetes was considered and rejected for this stage: it is designed to orchestrate many services at production scale and would add operational complexity disproportionate to a 3-service MVP (frontend, backend, database).
- Podman was considered as a Docker alternative; Docker was kept as the default due to wider tooling support, documentation, and familiarity, which matters for an academic deliverable that may be reviewed by others.

---

## 3. Services and containers

| Service | Container | Notes |
|---|---|---|
| Frontend | `frontend` | Static HTML/TS/CSS, served via a lightweight web server (e.g. Nginx) inside its own container once built |
| Backend | `backend` | FastAPI application, served via Uvicorn |
| Worker | `worker` | Celery worker process consuming async tasks (PDF analysis per Spec D07). Shares the backend codebase and runs as a separate container so failures or load on async work do not affect HTTP request handling. |
| Database | `db` | PostgreSQL, containerized in **both** local development and production, for environment parity |
| Message broker | `redis` | Redis, used by Celery as task queue and result backend. Containerized in both environments. |

Using containerized PostgreSQL and Redis in both environments (rather than managed cloud services only in production) ensures the database and broker behave identically wherever the system runs, and keeps the option open to run the entire stack locally with zero cloud dependency, fully in line with the project's portability goal. Migration to managed services (e.g. Azure Database for PostgreSQL, Azure Cache for Redis) remains possible later as a drop-in replacement, without changing application code — only the connection configuration.

---

## 4. Environment configuration

- Each service reads configuration from environment variables (see Spec 00b — Security Practices, Section 3).
- A `docker-compose.yml` defines all three services for local development, with volumes for database persistence and source code mounting for hot-reload during development.
- A separate, production-oriented Compose/deployment configuration is created when the system is first deployed (not defined yet — deferred until the MVP is functionally complete locally).

---

## 5. Deployment strategy (v1)

- **Manual deployment** for the MVP: no CI/CD pipeline is set up at this stage, by explicit decision, to keep early iterations simple.
- Target environment: Microsoft Azure, using Azure Container Apps (or Azure App Service for Containers) for `frontend`/`backend`, and either a containerized PostgreSQL or Azure Database for PostgreSQL Flexible Server for `db`.
- CI/CD automation (e.g. GitHub Actions building and pushing images, automatic deployment on merge) is deferred to a future iteration once the manual deployment process is validated and stable. This is recorded here so it is not forgotten, not because it is unimportant.

**Realized by:** the system was first deployed to Azure on 2026-07-07/08. **`specs/changesets/changeset-c09-azure-deployment.md` is the canonical, up-to-date production runbook** — architecture actually deployed, resource names, the exact redeploy commands (§4), and every gotcha found running this in production (§5). Whoever redeploys to production reads that document, not just this one; this spec records the original strategy decision, C09 records how it actually works today.

---

## 6. Rationale

This spec deliberately avoids any tool or service with a recurring cost or vendor lock-in: Docker has no licensing cost at this project's scale, Docker Compose has no cloud dependency, and PostgreSQL is run the same way locally and in the cloud. This directly supports the stated goal of being able to move the deployment target (Azure today, possibly another provider or fully local later) without re-architecting the system.
