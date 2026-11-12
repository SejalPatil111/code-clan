# Code Clan

Code Clan is the coding and programming assessment module of Department Workspace — an
AI-assisted collaborative coding and programming-learning platform (final-year engineering project).

## Purpose

Code Clan provides students with:

- Coding practice
- Programming assignments
- Coding tests
- Automated code execution & grading (`Python 3.11`, `C`, `C++17`, `Java`, `JavaScript`)
- Competitions and hackathons
- Performance analytics
- AI-assisted learning

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 19 + Vite 8 (`frontend/`) |
| Backend | Python 3.11, FastAPI, Uvicorn (`backend/`) |
| Grader Worker | Separate Docker worker (`backend/app/grading/worker.py`, `backend/Dockerfile.grader`) |
| Execution Sandbox | Ephemeral isolated container (`codeclan-sandbox:latest`, `backend/sandbox/`) |
| ORM | SQLAlchemy 2 (PyMySQL driver) |
| Database | MySQL (Windows MySQL80 locally, or MySQL 8.4 in Docker) |
| Auth | PBKDF2 password hashing + HMAC-signed bearer tokens (`backend/app/auth.py`) |
| Dev environment | Docker + Docker Compose |

> The original plan listed PostgreSQL and Judge0. The implementation uses **MySQL** and a **free, self-hosted isolated Docker sandbox grader** (no paid execution APIs such as Judge0).

## Project Structure

```
code-clan/
├── docker-compose.yml      # Docker stack (mysql, sandbox, grader, backend, frontend)
├── .env.example            # Template for the root .env used by docker compose
├── docs/
│   └── CODE_EXECUTION_DESIGN.md  # Phase 2 sandbox & automated grading architecture
├── backend/
│   ├── Dockerfile          # FastAPI backend image (no Docker socket)
│   ├── Dockerfile.grader   # Separate grader worker image (with Docker CLI)
│   ├── main.py             # FastAPI app + all routes + lightweight schema migrations
│   ├── requirements.txt
│   ├── .env                # (git-ignored) DATABASE_URL for the non-Docker workflow
│   ├── sandbox/            # Ephemeral sandbox image (Python, GCC/G++, OpenJDK, Node.js)
│   │   ├── Dockerfile
│   │   └── sandbox_runner.py
│   └── app/
│       ├── auth.py · database.py · models.py · schemas.py
│       └── grading/        # comparison.py · sandbox.py · worker.py
└── frontend/
    ├── Dockerfile
    ├── vite.config.js      # /api proxy -> FastAPI
    └── src/                # App.jsx, api.js, components/
```

---

## Running with Docker (Windows)

### 1. Prerequisites

- **Docker Desktop for Windows** (WSL 2 backend), with Docker Compose v2 (`docker compose ...`).
- **Git**.
- Free host ports **5173** (frontend), **8000** (API) and **3307** (Docker MySQL).
  Your Windows MySQL service keeps using **3306** — the two never conflict.

### 2. Start Docker Desktop

Start Docker Desktop from the Start menu and wait until it shows *Engine running*. Check in PowerShell:

```powershell
docker version
docker compose version
```

### 3. Configure the environment file

From the project root (`C:\Users\DELL\Documents\Projects\code-clan`):

```powershell
copy .env.example .env
notepad .env
```

Set at least:

| Variable | Purpose |
|---|---|
| `MYSQL_PASSWORD` | Password of the app user in the **Docker** MySQL (letters/digits/`-`/`_` only) |
| `MYSQL_ROOT_PASSWORD` | Root password of the **Docker** MySQL |
| `SECRET_KEY` | Signs login tokens. Generate: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

Optional: `MYSQL_DATABASE`, `MYSQL_USER`, `DB_HOST` (`mysql`), `DB_PORT` (3306), `MYSQL_HOST_PORT` (3307),
`BACKEND_HOST` (`0.0.0.0`), `BACKEND_PORT` (8000), `FRONTEND_PORT` (5173), `CORS_ORIGINS`, `VITE_API_BASE_URL` (`/api`), `SQL_ECHO`.

> [!IMPORTANT]
> `.env` is git-ignored — never commit it. `VITE_*` variables are compiled into browser code, so
> **never** put secrets in them. MySQL credentials are applied only when the Docker database volume is
> **first** created; changing them later does not change an existing database.

### 4. Start the project

```powershell
docker compose config      # validate configuration (prints resolved values, incl. secrets - don't share the output)
docker compose build       # build the frontend and backend images
docker compose up -d       # start mysql -> backend (waits for MySQL health) -> frontend
docker compose ps          # all three should be "running"; mysql and backend "(healthy)"
```

On first start the backend creates the tables in the empty Docker database using the project's
existing mechanism (`Base.metadata.create_all` + the small migration in `backend/main.py`).

### 5. Open the application

| What | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API (Swagger docs) | http://localhost:8000/docs |
| API (ReDoc) | http://localhost:8000/redoc |
| API health (incl. DB check) | http://localhost:8000/health |

The Docker database starts **empty**: register new teacher/student accounts at http://localhost:5173.

### 6. View logs

```powershell
docker compose logs -f              # all services
docker compose logs -f backend      # one service
docker compose logs --tail 100 mysql
```

### 7. Stop the services

```powershell
docker compose stop     # stop containers, keep them
docker compose down     # remove containers + network; the database volume is KEPT
```

> [!CAUTION]
> Do **not** use `docker compose down -v` (or `docker volume rm codeclan_mysql_data`) as routine
> cleanup — `-v` deletes the `mysql_data` volume and with it every user, problem and submission stored
> in the Docker database.

### 8. Rebuild after code changes

- **Python / React source changes** are picked up automatically (hot reload via bind mounts:
  Uvicorn `--reload`, Vite HMR with polling). Just refresh the browser.
- **`backend/requirements.txt` changed:**
  `docker compose up -d --build backend`
- **`frontend/package.json` / `package-lock.json` changed** (`-V` refreshes only the anonymous
  `node_modules` volume; the named database volume is not touched):
  `docker compose up -d --build -V frontend`
- **Dockerfile / compose changes:** `docker compose up -d --build`

### 9. Database persistence, backups and restore

Docker MySQL data lives in the named volume **`codeclan_mysql_data`**. It survives
`docker compose stop`, `down`, rebuilds and PC restarts.

**Which database am I using?**

| | Windows MySQL (existing) | Docker MySQL (new) |
|---|---|---|
| Runs as | Windows service `MySQL80` | Container `codeclan-mysql-1` |
| Host port | `localhost:3306` | `localhost:3307` |
| Used by | Non-Docker backend (`backend/.env`) | Docker backend (host `mysql:3306` inside Docker) |
| Data stored in | MySQL data dir on Windows | Docker volume `codeclan_mysql_data` |
| Credentials | Your existing ones | `MYSQL_USER` / `MYSQL_PASSWORD` from root `.env` |

They are completely separate; nothing is copied between them automatically. To check from a SQL
client, connect and run `SELECT @@hostname, @@port;` (Docker shows a container ID as hostname).

**Status / inspect:**

```powershell
docker compose ps mysql
"SHOW TABLES; SELECT COUNT(*) AS users FROM users;" | docker compose exec -T mysql sh -c 'MYSQL_PWD=$MYSQL_PASSWORD mysql -u$MYSQL_USER $MYSQL_DATABASE'
```

MySQL Workbench / DBeaver: host `127.0.0.1`, port `3307`, user/password from `.env`.

**Back up the Docker database** (writes a clean UTF-8 `.sql` file on Windows without PowerShell BOM issues; `backups/` and `*.sql` are git-ignored):

```powershell
mkdir backups -Force
docker compose exec -T mysql sh -c 'MYSQL_PWD=$MYSQL_PASSWORD mysqldump --no-tablespaces --single-transaction --routines -u$MYSQL_USER $MYSQL_DATABASE > /tmp/codeclan_backup.sql'
docker compose cp mysql:/tmp/codeclan_backup.sql "backups\codeclan_docker_$(Get-Date -Format yyyyMMdd_HHmm).sql"
```

**Restore a backup into the Docker database** (overwrites tables contained in the dump — back up first):

```powershell
docker compose cp backups\codeclan_docker_YYYYMMDD_HHMM.sql mysql:/tmp/restore.sql
docker compose exec -T mysql sh -c 'MYSQL_PWD=$MYSQL_PASSWORD mysql -u$MYSQL_USER $MYSQL_DATABASE < /tmp/restore.sql'
```

**Optional: copy data from the Windows database into Docker** (read-only on the Windows side;
run it only when you decide to — `--result-file` avoids PowerShell's UTF-16 `>` redirection):

```powershell
& "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" -h 127.0.0.1 -P 3306 -u codeclan_user -p --no-tablespaces --single-transaction --result-file=backups\codeclan_windows.sql codeclan
docker compose cp backups\codeclan_windows.sql mysql:/tmp/restore.sql
docker compose exec -T mysql sh -c 'MYSQL_PWD=$MYSQL_PASSWORD mysql -u$MYSQL_USER $MYSQL_DATABASE < /tmp/restore.sql'
```

### 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `error during connect` / `cannot find the file specified` | Docker Desktop is not running — start it and wait for *Engine running*. |
| `required variable MYSQL_PASSWORD is missing` | Create `.env` from `.env.example` in the project root. |
| `port is already allocated` / `bind: ... 5173/8000/3307` | Stop the non-Docker frontend/backend, or change `FRONTEND_PORT` / `BACKEND_PORT` / `MYSQL_HOST_PORT` in `.env`. |
| Backend `Access denied for user` | The volume was initialised with different credentials. Put the original values back in `.env`. (Recreating the volume deletes its data — back up first.) |
| Backend restarts / `Can't connect to MySQL server on 'mysql'` | `docker compose logs mysql`; the backend retries automatically and Compose restarts it. |
| Frontend shows "Login failed"/network errors | `docker compose logs backend`; check http://localhost:8000/health. |
| `mysql` stays `(health: starting)` on first run | First initialisation takes ~30–60 s. Watch `docker compose logs -f mysql`. |
| Code changes not reloading | Polling is enabled; give it a few seconds, or `docker compose restart backend frontend`. |
| Frontend error about missing modules after editing `package.json` | `docker compose up -d --build -V frontend` |

### 11. Returning to the non-Docker workflow

Docker is optional; the original workflow is unchanged and still uses your **Windows MySQL** via
`backend/.env`.

```powershell
docker compose stop          # free ports 8000 / 5173 (data is kept)

# Terminal 1 - backend (uses backend/.env -> Windows MySQL on localhost:3306)
cd C:\Users\DELL\Documents\Projects\code-clan
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd backend
uvicorn main:app --reload

# Terminal 2 - frontend
cd C:\Users\DELL\Documents\Projects\code-clan\frontend
npm install
npm run dev                  # http://localhost:5173 (proxies /api -> 127.0.0.1:8000)
```

Optional for the non-Docker backend: add `SECRET_KEY=...` to `backend/.env` (otherwise a built-in
development default is used) and `CORS_ORIGINS=...` if you serve the frontend from another origin.

---

## Docker architecture

```
Browser ──► localhost:5173  frontend (Vite dev server, node:22)
                │  /api/* proxied to http://backend:8000  (Docker network)
                ▼
            backend (FastAPI/Uvicorn, python:3.11, non-root, NO docker.sock)  ◄── localhost:8000 (docs, direct API)
                │  ├── mysql+pymysql://…@mysql:3306/codeclan
                │  └── http://grader:8090/internal/run-samples (internal Docker network only)
                ▼
            grader (Python worker + Docker CLI, polls MySQL `SELECT ... FOR UPDATE SKIP LOCKED`)
                │  spawns ephemeral containers (`--network none --read-only --tmpfs /work ...`)
                ▼
            codeclan-sandbox:latest (Python 3.11, GCC/G++, OpenJDK, Node.js, UID 65534:65534)
```

All published ports (`5173`, `8000`, `3307`) are bound to `127.0.0.1` (not reachable from your LAN). The `grader` service has no published host ports.

## Automated Code Execution & Grading (Phase 2)

Code Clan includes a full, self-hosted code execution and automated grading system:

- **Supported Languages:**
  - **Python 3.11** (`python3 -I -B`)
  - **C (C11)** (`gcc -O2 -std=c11`)
  - **C++ (C++17)** (`g++ -O2 -std=c++17`)
  - **Java (OpenJDK)** (`javac` + `java Main`)
  - **JavaScript (Node.js)** (`node --check` + `node`)
- **Separate Grader Service (`grader`):**
  - Arbitrary student code **never** executes inside the FastAPI process or container.
  - `POST /submissions` saves a submission with `status = "Pending Evaluation"` and `score = 0.0`.
  - `grader` atomically claims pending submissions (`SELECT ... FOR UPDATE SKIP LOCKED`), recovers stale `Running` jobs on worker restart, runs public and hidden test cases inside ephemeral `codeclan-sandbox:latest` containers, writes `submission_results` rows, and updates `status`, `score`, `passed_count`, `total_count`, `execution_time`, `error_message`, and `evaluated_at`.
- **Real Sample Execution (`POST /submissions/run-samples`):**
  - Authenticated and rate-limited (15 runs/min/student).
  - Executes only public (`is_hidden = False`) sample test cases and returns per-sample outputs without creating a submission or awarding XP.
- **Supported Verdicts:**
  - `Pending Evaluation`, `Running`, `Accepted`, `Wrong Answer`, `Time Limit Exceeded`, `Runtime Error`, `Compilation Error`, `Internal Evaluation Error`.
- **Hidden Test Case Protection:**
  - Hidden testcase inputs, expected outputs, and actual outputs are never returned to student endpoints (`/problems`, `/problems/{id}`, `/submissions/run-samples`, or student `GET /submissions/{id}`). Students see only aggregate hidden counts (`passed / total`). Teachers can inspect full hidden test cases and `teacher_hidden_results`.
- **Transparent Scoring & XP:**
  - Problem score is proportional to passed test cases: `max_score * (passed_count / total_count)`.
  - Student XP is computed deterministically from the student's best evaluated pass ratio per unique practice/assignment problem (up to 10 XP/problem) plus best evaluated coding-test problem scores. Clicking "Submit" or "Finish Test" without passing test cases awards `0 XP`, and repeated submissions never create duplicate XP.

Full architecture and security details are documented in [docs/CODE_EXECUTION_DESIGN.md](docs/CODE_EXECUTION_DESIGN.md).

### Development vs Production Security Notes

- **Sandbox isolation:** Every student run executes with `--network none`, `--read-only` rootfs, `--tmpfs /work:rw,exec,nosuid,nodev,size=32m`, `--memory 256m --memory-swap 256m`, `--cpus 0.5`, `--pids-limit 64`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--user 65534:65534`, scrubbed environment variables, 64 KB output caps, and wall-clock timeouts.
- **Remaining Docker trade-offs:** Because `grader` mounts `/var/run/docker.sock` to spawn sibling sandbox containers and standard Docker containers share the host kernel, a public internet deployment should run `grader` on a dedicated worker VM, restrict socket API calls via a Docker socket proxy, and use a sandboxed runtime such as **gVisor (`runsc`)** or **Firecracker microVMs**.

## Feature status

| Feature | Status |
|---|---|
| Registration / login / role-based route protection | Implemented & hardened (PBKDF2 + HMAC bearer tokens) |
| Student & teacher dashboards, progress analytics, roster | Implemented |
| Question bank (create/list problems, public & hidden test cases) | Implemented |
| Assignments & timed proctored coding tests | Implemented with real sandbox grading |
| Submissions history & teacher code/testcase review | Implemented |
| Leaderboard & deterministic XP | Implemented (derived from evaluated test cases) |
| Code execution & automated grading (Python, C, C++, Java, JS) | Implemented & verified |
| Competitions | UI placeholder (static row; DB tables exist, no API) |
| AI Mentor / AI Teaching Assistant | UI placeholder ("Under Integration") |
