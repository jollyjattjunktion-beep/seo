# Preet Sports — Advanced YouTube SEO Generator

A browser-based Streamlit app upgraded from the original command-line prototype. It generates cricket-match or general-video metadata, researches public YouTube competitor videos through YouTube Data API v3, checks basic field limits, and saves reusable Preet Sports defaults.

## Included

- Three title options per topic/match.
- Match-specific descriptions, searchable tags, and hashtags.
- Public competitor research for up to 50 videos, including available views, likes, comments, upload dates, and video tags.
- A transparent 0–100 checklist score with strengths and recommended improvements.
- Export to TXT, JSON, and CSV.
- Editable channel defaults stored in `data/preet_preferences.json` locally.
- Windows launcher (`run_windows.bat`) and Render Blueprint (`render.yaml`).

The old script's spaCy/NLTK model downloads and random analytics estimates have been removed. Random mock views/likes are misleading for SEO decisions, so the app displays actual public API counts when available and labels hidden data as unavailable.

## Run on Windows

1. Install Python 3.11 (64-bit) and ensure the Python launcher (`py`) is available.
2. Extract this folder to a location you can write to.
3. Double-click `run_windows.bat`. It creates `.venv`, installs dependencies, creates `.env` from `.env.example` if needed, and starts Streamlit.
4. Open the local URL printed in the terminal (normally `http://localhost:8501`).
5. Add your YouTube Data API key in the sidebar, or set `YOUTUBE_API_KEY` in `.env` and restart the app.

### Create a YouTube Data API key

In [Google Cloud Console](https://console.cloud.google.com/), create/select a project, enable **YouTube Data API v3**, then create an API key. Restrict the key to the YouTube Data API v3 API. Do not commit a real key to GitHub or paste it into a source file. Search uses `search.list` and video statistics/tags use `videos.list`; public API quotas and availability apply.

## Push to GitHub

Create an empty repository on GitHub, then run these commands from this project folder:

```bash
git init
git add .
git commit -m "Build Preet Sports YouTube SEO Generator"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Replace the remote URL with your repository's actual URL. `.env` and the local preferences JSON are excluded by `.gitignore`.

## Deploy to Render

1. Push the project to GitHub.
2. In Render, create a **Blueprint** and connect the repository containing `render.yaml`.
3. Set the secret `YOUTUBE_API_KEY` in Render when prompted.
4. The Blueprint uses a paid Starter web service and a 1 GB persistent disk mounted at `/var/data`, so saved defaults can survive redeployments. Review Render's current price before creating the service.
5. Deploy and open the generated `onrender.com` URL.

Render's persistent disk is not available on its Free web-service plan. The included configuration deliberately chooses persistent storage rather than silently losing preferences on redeploy. To test without paid persistent storage, remove the `disk` block, change `plan: starter` to `plan: free`, and set `DATA_DIR` to a normal writable directory; preferences may then be lost when Render restarts/redeploys the service.

## What the score means

The displayed score is a simple, inspectable checklist for title length, phrase placement, description usefulness, tag-field size, hashtag count, and calls to action. It is **not** YouTube's internal score, a ranking signal, or a prediction of views or CTR. YouTube says tags usually play a minimal role in discovery; accurate content, a strong title/thumbnail, and a useful description matter more.

Public competitor statistics are a snapshot. Private analytics such as impressions, click-through rate, watch time, and revenue require separate OAuth authorization to YouTube Analytics and are not included here. Tags from competitor results may be absent because public tag availability varies. Do not copy irrelevant terms simply because competitors used them.

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Main files

- `app.py` — Streamlit UI.
- `seo_engine.py` — title/description/tag generation and heuristic score.
- `youtube_api.py` — public YouTube Data API requests.
- `preferences.py` — saved defaults.
- `render.yaml` — Render deployment Blueprint.
