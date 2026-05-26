# Deploying ChatARPES

Target setup: **Fly.io** (backend) + **Cloudflare Pages** (frontend) + **Cloudflare Access** (single-user auth). Expected cost: **under $10/month** for one supervisor's usage.

---

## 0. Prerequisites (one-time, ~10 min)

- Install Fly CLI: `brew install flyctl` then `fly auth signup` (or `fly auth login`).
- A Cloudflare account (free) and a domain you control on Cloudflare. If you don't have a domain, you can still deploy and use the auto-assigned `*.pages.dev` URL — but Cloudflare Access for `*.pages.dev` requires a domain on your account. Easiest path: buy a cheap domain (`.dev`/`.app` ~$12/yr) and point its nameservers at Cloudflare.
- Your `ANTHROPIC_API_KEY`.

---

## 1. Deploy the backend to Fly.io

From the repo root:

```bash
# 1. Claim a unique app name (edit fly.toml afterward if you change it)
fly launch --copy-config --no-deploy
# Answer "No" to Postgres/Redis/Tigris when prompted.

# 2. Set secrets — these never touch git
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly secrets set ALLOWED_ORIGINS=https://YOUR-FRONTEND.pages.dev
#   ^^ you'll update this in step 2 once you know the Pages URL

# 3. Deploy
fly deploy
```

Verify: `curl https://<your-app>.fly.dev/health` → `{"status":"ok"}`.

Note the URL — you'll need it for the frontend.

---

## 2. Deploy the frontend to Cloudflare Pages

1. Push this repo to GitHub (or GitLab) if it isn't already.
2. Cloudflare dashboard → **Workers & Pages** → **Create application** → **Pages** → **Connect to Git** → pick this repo.
3. Build settings:
   - **Framework preset:** Vite
   - **Build command:** `npm run build`
   - **Build output directory:** `dist`
   - **Root directory:** `frontend`
4. Under **Environment variables (Production)**, add:
   - `VITE_API_URL` = `https://<your-app>.fly.dev`
5. Hit **Save and Deploy**. Wait ~2 min for the first build.

Note the assigned URL (e.g. `https://chatarpes.pages.dev`). Then go back and update the backend's allowed origins:

```bash
fly secrets set ALLOWED_ORIGINS=https://chatarpes.pages.dev
```

Test in a private browser window — uploads and chat should work.

---

## 3. Restrict access to your supervisor (Cloudflare Access)

This is the "only she can see it" piece. **Free** for up to 50 users.

1. Cloudflare dashboard → **Zero Trust** → first-time setup picks a team subdomain (e.g. `your-lab.cloudflareaccess.com`). Pick "Free" plan when prompted (requires a credit card on file but won't charge for ≤50 users).
2. **Settings** → **Authentication** → add **One-time PIN** as a login method (no extra config — emails a 6-digit code).
3. **Access** → **Applications** → **Add an application** → **Self-hosted**:
   - **Application name:** ChatARPES
   - **Application domain:** `chatarpes.pages.dev` (or your custom domain)
   - Leave the rest at defaults; click **Next**.
4. **Add a policy**:
   - **Policy name:** Lab supervisor
   - **Action:** Allow
   - **Configure rules → Include → Emails:** `supervisor@example.edu`
   - Add your own email too so you don't lock yourself out.
   - Click **Next** → **Add application**.
5. **Repeat for the backend:** add a second Access application for `<your-app>.fly.dev` with the same policy. This prevents anyone from hitting the API directly.

Now anyone visiting either URL sees a Cloudflare login screen, enters their email, gets a 6-digit code, and is in. Everyone else is blocked.

> **Important:** Cloudflare Access works by sitting in front of traffic that flows through Cloudflare. The `*.pages.dev` URL is automatically proxied. To protect the Fly backend you have two options:
>
> - **Easy:** put a custom domain on the backend (`api.yourdomain.com`) on Cloudflare, set it to proxied (orange cloud), and CNAME it to `<your-app>.fly.dev`. Then Access can protect it.
> - **Easier still:** skip Access on the backend and rely on the CORS allowlist + rate limiting already configured. Anyone who knows the Fly URL can hit it directly, but they can't render the UI without your frontend, and CORS blocks browser-based abuse. For a single private demo this is usually fine.

---

## 4. Cost guardrails (do this before sharing the URL)

1. **Anthropic console** → Settings → **Limits** → set a hard monthly spend cap (e.g. $20). This is the most important step.
2. **Fly.io** → Billing → set a spend alert.
3. Confirm `LLM_MODEL=claude-haiku-4-5-20251001` in `fly.toml` (already set). Haiku is ~12× cheaper than Sonnet for this workload.

---

## 5. Updating later

- **Backend changes:** `fly deploy` from repo root.
- **Frontend changes:** `git push` — Cloudflare Pages auto-deploys.
- **Rotate the API key:** `fly secrets set ANTHROPIC_API_KEY=sk-ant-...` (triggers a rolling restart automatically).

---

## Troubleshooting

- **CORS error in browser console:** check that `ALLOWED_ORIGINS` on Fly exactly matches the Pages URL (no trailing slash, include `https://`). After changing, run `fly deploy` (secrets reload on next start).
- **"Out of memory" during `.pxt` processing:** bump `memory_mb = 1024` in `fly.toml` and redeploy.
- **Rate-limit (429) errors:** raise the limit in `backend/app/main.py` (`default_limits=["60/minute"]`).
- **Access loop / 1-hour login expiry too short:** Zero Trust → Settings → Authentication → session duration.
