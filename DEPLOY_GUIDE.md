# Deploying TradeEdge AI to your live website (Sprint 9)

This connects the Python backend to your real site at
`https://tradeedge3.netlify.app/` (GitHub repo:
`kevinsongolo-netizen/tradeedge1`). Three steps: host the backend
online, point it at a real database, then add one script block to your
site.

## Step 1 — Get your Supabase Postgres connection string

1. Go to `https://supabase.com/dashboard/project/xlsybhevtoizfyyiggqg/settings/database`.
2. Under **Connection string**, choose the **URI** tab.
3. Copy the string — it looks like
   `postgresql://postgres:[YOUR-PASSWORD]@db.xlsybhevtoizfyyiggqg.supabase.co:5432/postgres`.
4. Replace `[YOUR-PASSWORD]` with your actual database password (Supabase
   shows a "reveal" option, or you set it under Database settings if
   you don't have it saved).
5. Change `postgresql://` at the very start to `postgresql+asyncpg://`
   — keep everything else exactly the same. This is the value you'll
   paste into Render as `DATABASE_URL`.

## Step 2 — Deploy the backend to Render (free)

1. Push this `tradeedge-backend` folder to a new GitHub repo (or reuse
   an existing one) — Render deploys from a GitHub repo.
2. Go to `https://render.com`, sign up (free), click **New +** ->
   **Blueprint**.
3. Connect your GitHub account and pick the repo you just pushed.
   Render will read `render.yaml` (already included) and pre-fill most
   settings.
4. When prompted for `DATABASE_URL`, paste the connection string from
   Step 1.
5. Click **Apply** / **Create**. First deploy takes a few minutes.
6. Once live, Render shows a URL like
   `https://tradeedge-backend-xxxx.onrender.com` — this is your
   backend's permanent address. Save it.
7. Visit `<that-url>/healthz` in your browser — it should show
   `{"status":"ok"}`. If so, the backend is live.
8. Visit `<that-url>/docs` to confirm the same interactive page you
   saw locally now works from the internet.

Note: Render's free tier "spins down" after 15 minutes of no traffic
and takes ~30-60 seconds to wake back up on the next request — normal
and fine for personal use, just don't be alarmed by the first request
of the day feeling slow.

## Step 3 — Run the database setup once

Render's free plan doesn't give you a persistent terminal, so run this
one time from your own computer instead, pointed at the same database:

```
cd tradeedge-backend
.venv\Scripts\Activate.ps1
$env:DATABASE_URL="postgresql+asyncpg://postgres:<password>@db.xlsybhevtoizfyyiggqg.supabase.co:5432/postgres"
alembic upgrade head
```

(On Windows PowerShell, `$env:NAME="value"` sets a variable for that
one terminal session only — safe, doesn't touch your local `.env`.)

## Step 4 — Add AI Insights to your website

1. Open `tradeedge-ai-insights-snippet.html` (provided alongside this
   guide).
2. Go to `https://github.com/kevinsongolo-netizen/tradeedge1/blob/main/index.html`,
   click the pencil (edit) icon.
3. Find the line with `<nav class="nav-tabs">` and, among the other
   `<button class="nav-tab" ...>` lines nearby, add the one commented
   line from the top of the snippet file:
   `<button class="nav-tab" data-tab="ai-insights">AI Insights</button>`
4. Scroll to the very bottom of the file. Right before the final
   `</body>` line, paste the rest of the snippet file's contents (the
   `<div class="tab-content" id="tab-ai-insights">...</div>` block and
   the `<script>...</script>` block together).
5. Scroll down, add a commit message like "Add AI Insights tab", and
   click **Commit changes directly to the main branch**.
6. Netlify auto-redeploys within a minute or two (it's already
   connected to this GitHub repo).

## Step 5 — Try it

1. Open `https://tradeedge3.netlify.app/`, go to the new **AI Insights**
   tab.
2. Paste your Render URL from Step 2 into the **Backend URL** box,
   click **Save**.
3. Click **Sync my trades to AI backend** — this sends your existing
   journal entries to the Python backend so it has real data.
4. Click **Load insights** under Coach Deep Dive to see why-losing/
   why-winning/best-setup analysis from your real trades.
5. Try **Pre-Trade Check** with a pair and direction to get a live
   recommendation.

## If something doesn't work

- Blank/error under AI Insights: open your browser's dev console (F12)
  on the Errors tab and check for a red CORS error — if so, the
  `CORS_ORIGINS` Render env var needs to include your exact Netlify
  URL (it's pre-set to `https://tradeedge3.netlify.app` in
  `render.yaml`, but double check it matches exactly, including
  https://, no trailing slash).
- "Backend URL first" message: you haven't pasted+saved the Render URL
  in the AI Insights tab yet.
- Sync says trades failed: open the browser console (F12) for the
  specific error per trade — usually a data type mismatch, tell me the
  exact error and I'll help.
