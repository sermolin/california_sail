# Slack setup

This is the path from a new Slack account to a working California Sail bot. Slack does not issue a single API key. California Sail needs two values from the app you create:

| Environment variable | What it is | Where Slack shows it |
|---|---|---|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token, starting with `xoxb-` | **OAuth & Permissions**, after you install the app |
| `SLACK_SIGNING_SECRET` | Signing secret Slack uses to sign every request | **Basic Information → App Credentials** |

Both must be set. If either is missing, `POST /slack/events` returns 503 and the bot stays off.

The bot is an HTTP app. Slack calls `POST /slack/events` on the California Sail API for slash commands and events. There is no polling mode. The API has to be reachable at a public HTTPS URL before Slack will accept the request URL. That URL is the API, not the Streamlit UI.

Create the Slack app once, then pick one way to run the API:

- [Local laptop deployment for development](#local-laptop-deployment-for-development) — uvicorn on your machine, exposed with ngrok.
- [GCP deployment](#gcp-deployment) — `california-sail-api` on Cloud Run.

Command names below are the ones registered in `app/bot/slack.py`. The name you create in the Slack dashboard has to match, including the leading slash.

---

## 1. Create a Slack account and workspace

1. Open [https://slack.com/get-started](https://slack.com/get-started).
2. Sign up with an email address. Confirm the address when Slack asks.
3. Create a workspace. The free plan is enough. A name such as `California Sail` is fine if this workspace exists only for the bot.
4. Finish the prompts until you land in the workspace.

If you already belong to a workspace, you can install the app there instead. You need permission to install apps. Some workspaces require an admin to approve the install.

---

## 2. Create the Slack app

1. Open [https://api.slack.com/apps](https://api.slack.com/apps) and sign in with the account from the previous step.
2. Click **Create New App**, then **From scratch** (or **Blank App**).
3. Set the app name to `California Sail` (this is the name people will @mention).
4. Pick the workspace you just created.
5. Click **Create App**. You land on **Basic Information**.

---

## 3. Copy the signing secret

1. On **Basic Information**, open **App Credentials**.
2. Click **Show** next to **Signing Secret**.
3. Copy it. This value is `SLACK_SIGNING_SECRET`.

Keep it out of git. It goes in `.env` for local development, or in Secret Manager for GCP. Never commit it.

---

## 4. Add bot scopes and install the app

The token does not exist until the app is installed into the workspace. The following steps are best done from the Slack web interface: https://app.slack.com/app

1. In the left sidebar, open **OAuth & Permissions**.
2. Scroll past token rotation, PKCE, and **Redirect URLs**. Leave those empty. California Sail uses a bot token from **Install to Workspace**, not an OAuth redirect.
3. Stop at **Bot Token Scopes**. Click **Add an OAuth Scope** on that section only. Leave **User Token Scopes** empty.

The scope box is a search field. It does not list every scope until you type the id. `commands` and `app_mentions:read` are bot scopes, so they never appear in the user-scope box. Type each id exactly, then click the match:

- `commands` has no colon. A search for `commands:` will not find it.
- `app_mentions:read` uses an underscore: `app_mentions`, not `app.mentions`.

| Scope | Why California Sail needs it |
|---|---|
| `commands` | Receive slash commands |
| `chat:write` | Post replies |
| `app_mentions:read` | Receive `@California Sail` mentions |
| `im:history` | Receive direct messages |
| `im:read` | See the DM conversation the bot is in |
| `im:write` | Open a direct-message conversation with a user |

4. Scroll back to the top of **OAuth & Permissions** and click **Install to Workspace**.

Slack shows **Please add at least one feature or permission scope below to install your app** while that bot-scope table still says no OAuth scope has been added. **Install to Workspace** stays disabled until at least one bot scope is listed. A redirect URL does not clear that message.
5. Review the permissions and click **Allow**.
6. Copy **Bot User OAuth Token**. It starts with `xoxb-`. This value is `SLACK_BOT_TOKEN`.

If you add or remove a scope later, Slack does not apply it until you click **Reinstall to Workspace**.

---

## 5. Let people message the bot

1. Open [https://api.slack.com/apps](https://api.slack.com/apps), select **California Sail**, then open **App Home** in the left sidebar. This setting is not in the Slack conversation itself.
2. Under **Show Tabs**, turn on **Messages Tab**.
3. Check **Allow users to send Slash commands and messages from the messages tab**.

Until that box is checked, the message field in the app conversation says **Messaging has been disabled for this application**. Reload the conversation after saving. Direct messages still need the `message.im` event from [Register slash commands and events](#register-slash-commands-and-events) before the API receives them.

---

## Register slash commands and events

Do this after the API is reachable. The request URL depends on where the API is running. Use the URL from [local laptop deployment](#local-laptop-deployment-for-development) or [GCP deployment](#gcp-deployment). Paste that same URL on every slash command and on Event Subscriptions.

Slack immediately sends a URL check when you save. The Bolt handler answers it. A 503, a connection error, or a signature failure means the check fails and Slack refuses to save the URL. Start the API with both secrets loaded before you paste the URL.

### Slash commands

1. In the left-side panel of your app, under **Features**, open **Slash Commands** and click **Create New Command** once per row.
2. Set **Request URL** on every command to the deployment URL.
3. Use these names. A different name, such as `/sail-forecast`, will not reach a handler.

| Command | Usage hint | Short description |
|---|---|---|
| `/regions` | | List sailing regions |
| `/zones` | `<region_id>` | List zones in a region |
| `/profiles` | | List sailor profiles |
| `/forecast` | `<zone_id> [profile_id]` | Forecast for one zone |
| `/compare` | `<region_id> [profile_id]` | Rank zones in a region |
| `/windows` | `<zone_id> [profile_id]` | Best sailing windows |
| `/warnings` | `<region_id>` | Active marine warnings |
| `/explain` | `<zone_id> [profile_id]` | Explain a zone score |
| `/reset` | | Clear your conversation history |

`profile_id` is `school`, `cruiser`, or `racer`. When it is omitted, the bot uses `cruiser`.

Example that ranks places to sail on San Francisco Bay:

```text
/compare sf-bay cruiser
```

### Events

1. Open **Event Subscriptions** and turn **Enable Events** on.
2. Set **Request URL** to the same deployment URL. Wait until Slack shows that the URL is verified.
3. Under **Subscribe to bot events**, add:

| Event | What it delivers |
|---|---|
| `app_mention` | An @mention in a channel |
| `message.im` | A direct message to the bot |

4. Save changes.
5. Reinstall the app to the workspace if Slack asks you to. New event scopes do not apply to the old install.

Do not subscribe to `message.channels`. The bot only treats direct messages and @mentions as questions. Other channel traffic is ignored, and subscribing to it would send those messages to the API anyway.

---

## Local laptop deployment for development

Use this while you are changing the bot on your machine. Slack cannot call `http://localhost`, so ngrok publishes port 8080 as a temporary HTTPS URL.

### 1. Put the credentials in `.env`

```ini
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
```

Plain-language questions also need the OpenRouter agent. Slash commands work without it.

```ini
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=anthropic/claude-3-haiku
```

### 2. Start the API

```bash
source .venv/bin/activate
uvicorn app.api.main:app --reload --port 8080
```

Confirm the process is up:

```bash
curl -s http://localhost:8080/health
# → {"status":"ok"}
```

That only means the API is running. Slack status is in the **uvicorn terminal**, not in `/health`:

| Startup log | Meaning |
|---|---|
| `Slack bot enabled.` | Both `SLACK_BOT_TOKEN` and `SLACK_SIGNING_SECRET` were set |
| `SLACK_BOT_TOKEN or SLACK_SIGNING_SECRET not set — Slack bot disabled.` | One or both are empty |

Restart uvicorn after you edit `.env` so those lines are re-evaluated.

### 3. Expose port 8080 with ngrok

Leave uvicorn running and, in another terminal:

```bash
ngrok http 8080
```

Use the `https://` forwarding URL ngrok prints, plus `/slack/events`.

Example:

```text
https://canopener-bovine-joining.ngrok-free.dev/slack/events
```

### 4. Point Slack at the ngrok URL

1. Open [https://api.slack.com/apps](https://api.slack.com/apps) and select your app.
2. **Event Subscriptions → Enable Events → Request URL** — paste the ngrok URL and wait for the green **Verified** check.
3. Set **Request URL** on every slash command to that same URL.

ngrok URLs change when the tunnel restarts (unless you have a reserved domain). Update Slack each time the forwarding host changes.

---

## GCP deployment

Use this for the API that stays up on Cloud Run. Project `sermolin-2026`, region `us-west1`, service `california-sail-api`.

Slack request URL:

```text
https://california-sail-api-xbvh25hksq-uw.a.run.app/slack/events
```

Use that URL for Event Subscriptions and for every slash command. Do not point Slack at the Streamlit UI host.

### 1. Store the secrets

`scripts/deploy.sh` mounts `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, and `OPENROUTER_API_KEY` from Secret Manager. Create them once, then add a version for each value:

```bash
for S in TELEGRAM_BOT_TOKEN SLACK_BOT_TOKEN SLACK_SIGNING_SECRET OPENROUTER_API_KEY; do
  gcloud secrets create "$S" --project=sermolin-2026 || true
done

printf '%s' "$SLACK_BOT_TOKEN" | gcloud secrets versions add SLACK_BOT_TOKEN --data-file=- --project=sermolin-2026
printf '%s' "$SLACK_SIGNING_SECRET" | gcloud secrets versions add SLACK_SIGNING_SECRET --data-file=- --project=sermolin-2026
printf '%s' "$OPENROUTER_API_KEY" | gcloud secrets versions add OPENROUTER_API_KEY --data-file=- --project=sermolin-2026
```

Grant the Cloud Run service account access:

```bash
PROJECT_NUMBER=$(gcloud projects describe sermolin-2026 --format='value(projectNumber)')
for S in TELEGRAM_BOT_TOKEN SLACK_BOT_TOKEN SLACK_SIGNING_SECRET OPENROUTER_API_KEY; do
  gcloud secrets add-iam-policy-binding "$S" \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project=sermolin-2026
done
```

### 2. Deploy the API

```bash
./scripts/deploy.sh api
```

The script prints the Slack request URL when the deploy finishes. It is the Cloud Run service URL plus `/slack/events`. The current service URL is:

```text
https://california-sail-api-xbvh25hksq-uw.a.run.app/slack/events
```

`OPENROUTER_MODEL` defaults to `anthropic/claude-haiku-4.5`. Override it for one deploy with `OPENROUTER_MODEL=... ./scripts/deploy.sh api`.

### 3. Point Slack at the Cloud Run URL

1. Open [https://api.slack.com/apps](https://api.slack.com/apps) and select your app.
2. **Event Subscriptions → Enable Events → Request URL** — paste `https://california-sail-api-xbvh25hksq-uw.a.run.app/slack/events` and wait for the green **Verified** check.
3. Set **Request URL** on every slash command to that same URL.

If Slack's URL check returns 503, the revision started without `SLACK_BOT_TOKEN` or `SLACK_SIGNING_SECRET`. Confirm both secrets exist, then redeploy with `./scripts/deploy.sh api`.

---

## Invite the bot and try it

In a channel where you want to ask questions:

```text
/invite @California Sail
```

Then check each path:

| What you do | What should happen |
|---|---|
| `/regions` | A list of San Francisco Bay, Puget Sound, and Sardinia |
| `/compare sf-bay` | Zones in that region, ranked, with a verdict |
| A direct message: `Where should we sail on the Bay this afternoon?` | A short answer from the agent, if `OPENROUTER_API_KEY` is set |
| `@California Sail where should we sail on the Bay this afternoon?` | The same kind of answer in the channel |

The agent is told to compare zones and to check active warnings before it recommends a place. Slash commands do that comparison directly and do not need OpenRouter.

If the agent replies that it is not configured, `OPENROUTER_API_KEY` is missing. `/compare` and `/forecast` still work.

---

## When something fails

| What you see | What to check |
|---|---|
| Slack will not save the request URL | The API is running, both secrets are set, the URL ends in `/slack/events`, and the ngrok tunnel or Cloud Run service is up |
| `POST /slack/events` returns 503 | `SLACK_BOT_TOKEN` or `SLACK_SIGNING_SECRET` was empty when the process started |
| Slack says the command is unknown | The command was not created, or the name does not match the slash-command table |
| `/forecast` works, an @mention does nothing | `app_mention` is not subscribed, the app was not reinstalled, or the bot was not invited to the channel |
| A direct message does nothing | **Messages Tab** is off, or `message.im` is not subscribed |
| The mention replies with the "AI agent is not configured" text | Set `OPENROUTER_API_KEY` and restart the API (local) or redeploy (GCP) |
| Local URL check fails after a laptop reboot | ngrok issued a new host. Update Event Subscriptions and every slash command |
