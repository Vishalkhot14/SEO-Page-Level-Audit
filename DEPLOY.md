# Deploy your SEO Audit Tool as a real website (free)

This turns the tool into an actual website with a URL bar and drag-and-drop
upload — no code editing needed once it's live. Takes about 10 minutes,
one time only. Free forever on Streamlit Community Cloud.

## What you need
- A GitHub account (free) — github.com/signup, if you don't have one
- That's it. Streamlit Community Cloud signs in with GitHub, no separate account.

## Steps

1. **Create a GitHub repository**
   - Go to github.com, click the "+" top right → "New repository"
   - Name it anything (e.g. `seo-audit-tool`)
   - Set it to **Public** (required for the free tier)
   - Click "Create repository"

2. **Upload these files to it**
   - On your new repo's page, click "Add file" → "Upload files"
   - Drag in all the files from this folder: `app.py`, `requirements.txt`,
     `analyzer.py`, `content_gap.py`, `export_csv.py`, `export_dashboard.py`,
     `serp_analysis.py`, `llm_analysis.py`
   - Click "Commit changes"

3. **Deploy on Streamlit Community Cloud**
   - Go to share.streamlit.io
   - Click "Sign in with GitHub" and authorize it
   - Click "Create app" → "Deploy a public app from GitHub"
   - Pick your repository, branch `main`, and set the main file to `app.py`
   - Click "Deploy"
   - Wait ~1-2 minutes while it installs and starts

4. **You're live**
   - You'll get a URL like `https://your-app-name.streamlit.app`
   - Bookmark it — this is your permanent tool from now on
   - Anyone with the link can use it (don't put private API keys in the
     code itself — the app has boxes to paste keys in each time instead,
     so nothing sensitive is stored in the public repo)

## Updating it later
If you ever want to change something: edit the file on GitHub (or push a
new version), and Streamlit Cloud automatically redeploys within a minute.

## If you'd rather not make the repo public
Streamlit Community Cloud's free tier requires a public GitHub repo (the
code is visible, not your audit data — nothing you type into the app is
stored in the repo). If you need a private version, alternatives are
Streamlit Cloud's paid tier, or Hugging Face Spaces (also free, supports
private Spaces on paid plans only) — for a fully free + private option
you'd need a platform like Render.com's free tier, which is more setup.
Happy to walk through that instead if privacy matters more than the
extra steps.
