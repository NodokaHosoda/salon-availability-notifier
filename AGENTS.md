# Repository Guidelines

## Project Structure & Module Organization
This repository is a small Python service for watching Hot Pepper availability and notifying LINE users.

- `main.py`: Flask app for the LINE webhook, LIFF pages, and exception-date APIs.
- `scheduled_notifier.py`: scheduled notification runner that checks availability and pushes LINE messages.
- `templates/`: LIFF HTML views for adding or removing excluded dates.
- `static/`: LIFF frontend assets (`liff.css`, `liff.js`).
- `.github/workflows/playwright.yml`: scheduled GitHub Actions job that installs dependencies and runs `scheduled_notifier.py`.
- `Dockerfile` and `cloudbuild.yml`: container build and Cloud Run deployment support.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create and activate a local virtualenv.
- `pip install -r requirements.txt`: install Flask, Playwright, Supabase, and LINE SDK dependencies.
- `python -m playwright install`: install browser binaries required by `scheduled_notifier.py`.
- `python main.py`: run the Flask app locally on `0.0.0.0:${PORT:-8080}`.
- `python scheduled_notifier.py`: run the availability check once, using values from `.env`.
- `docker build -t hotpepper-watcher .`: verify the container build locally.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, snake_case for functions and variables, and uppercase names for environment-backed constants such as `SUPABASE_URL`. Keep Flask route handlers thin and move reusable logic into helper functions. Match the current style of direct, small functions instead of introducing large abstractions. There is no formatter configured yet, so keep imports grouped and lines readable.

## Testing Guidelines
There is no dedicated test suite in the repository today. Before opening a PR, run `python main.py` for basic route checks and `python scheduled_notifier.py` for a one-shot integration check with non-production credentials. If you add tests, prefer `pytest` under a new `tests/` directory and name files `test_<module>.py`.

## Commit & Pull Request Guidelines
Recent history mixes short Japanese summaries and small fix commits, for example `不具合修正とバックエンドの除外日の実装` and `fix db error`. Keep commits focused and descriptive; one logical change per commit. PRs should include the behavior change, any required env vars or Supabase schema updates, and screenshots for LIFF UI changes in `templates/` or `static/`.

## Security & Configuration Tips
Do not commit real secrets from `.env`. Required runtime values include LINE channel credentials, Supabase keys, `TASK_URL`, and `APP_BASE_URL`. Use test credentials when running the scheduled notifier locally because it can send live LINE push messages.
