# GitHub Upload Guide

`dist/live-agent-github-source.zip` is a source-only package. It excludes API keys, logs, temporary files, cloud build dependencies, historical reports, and raw livestream data.

## Publish Steps

1. Create an empty GitHub repository. Do not initialize it with a README, license, or .gitignore.
2. Extract `live-agent-github-source.zip` into a new local folder.
3. Run the following commands in that folder:

```powershell
git init
git add .
git status
git commit -m "feat: add livestream operations analysis agent"
git branch -M main
git remote add origin https://github.com/<your-account>/<your-repository>.git
git push -u origin main
```

## Before Deployment

- Configure `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, and `LIVE_AGENT_API_KEY` as platform environment variables.
- Replace the example server URL in `dify_openapi.yaml` with your own HTTPS service URL before importing it into Dify.
- Historical reports can be stored in `output/` locally or in a managed storage service. Do not commit real business reports with personal information.
