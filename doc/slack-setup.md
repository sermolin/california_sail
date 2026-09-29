# Slack setup

This is the path from a new Slack account to a working California Sail bot. Slack does not issue a single API key. California Sail needs two values from the app you create:

| Environment variable | What it is | Where Slack shows it |
|---|---|---|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token, starting with `xoxb-` | **OAuth & Permissions**, after you install the app |
| `SLACK_SIGNING_SECRET` | Signing secret Slack uses to sign every request | **Basic Information → App Credentials** |

Both must be set. If either is missing, `POST /slack/events` returns 503 and the bot stays off.

The bot is an HTTP app. Slack calls `POST /slack/events` on the California Sail API for slash commands and events. There is no polling mode. The API process has to be reachable at a public HTTPS URL before Slack will accept the request URL.

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
2. Click **Create New App**, then **From scratch**.
3. Set the app name to `California Sail` (this is the name people will @mention).
4. Pick the workspace you just created.
5. Click **Create App**. You land on **Basic Information**.

---

## 3. Copy the signing secret

1. On **Basic Information**, open **App Credentials**.
2. Click **Show** next to **Signing Secret**.
3. Copy it. This value is `SLACK_SIGNING_SECRET`.

Keep it out of git. It goes in `.env` or in the API service environment, never in the repository.

---

## 4. Add bot scopes and install the app

The token does not exist until the app is installed into the workspace.

1. In the left sidebar, open **OAuth & Permissions**.
2. Scroll past token rotation, PKCE, and **Redirect URLs**. Leave those empty. California Sail uses a bot token from **Install to Workspace**, not an OAuth redirect.
3. Stop at **Bot Token Scopes** (**Ámbitos de los tokens de usuarios bot**). Click **Add an OAuth Scope** (**Añadir un ámbito de OAuth**) on that section only. Leave **User Token Scopes** (**Ámbitos de los tokens de usuario**) empty.

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

Until that box is checked, the message field in the app conversation says **Se ha desactivado el envío de mensajes a esta aplicación.** Reload the conversation after saving. Direct messages still need the `message.im` event from section 9 before the API receives them.

---

## 6. Put the credentials where the API can read them

In the project `.env`:

```ini
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
```

Plain-language questions also need the OpenRouter agent. Slash commands work without it.

```ini
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=anthropic/claude-3-haiku
```

Start the API and confirm it is healthy:

```bash
source .venv/bin/activate
uvicorn app.api.main:app --reload --port 8080
```

```bash
curl -s http://localhost:8080/health
```

The log line `Slack bot enabled.` means both Slack variables were present at startup. `Slack bot disabled` means one of them is empty. Restart the process after you edit `.env`.

On the deployed API, set the same two variables on `california-sail-api`. `scripts/deploy.sh` currently mounts only `TELEGRAM_BOT_TOKEN`. Until the Slack values are on that service, `POST /slack/events` returns 503 and Slack's URL check fails.

---

## 7. Give Slack a public HTTPS URL

Slack cannot call `http://localhost`. The request URL must be HTTPS and must be the API, not the Streamlit UI.

| Where the API runs | Request URL |
|---|---|
| Your machine, through a tunnel | `https://<tunnel-host>/slack/events` |
| Cloud Run | `https://<california-sail-api host>/slack/events` |

For a tunnel while developing locally, leave uvicorn running on port 8080 and expose it. With [ngrok](https://ngrok.com/):

```bash
ngrok http 8080
```

Use the `https://` forwarding URL ngrok prints, plus `/slack/events`. Start the API with both secrets loaded before you save the URL in Slack. Slack immediately sends a URL check. The Bolt handler answers it. A 503, a connection error, or a signature failure means the check will fail and Slack will refuse to save the URL.

---

## 8. Register slash commands

1. Open **Slash Commands** and click **Create New Command** once per row.
2. Set **Request URL** on every command to the URL from the previous step.
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

---

## 9. Subscribe to events

1. Open **Event Subscriptions** and turn **Enable Events** on.
2. Set **Request URL** to the same `https://…/slack/events` URL. Wait until Slack shows that the URL is verified.
3. Under **Subscribe to bot events**, add:

| Event | What it delivers |
|---|---|
| `app_mention` | An @mention in a channel |
| `message.im` | A direct message to the bot |

4. Save changes.
5. Reinstall the app to the workspace if Slack asks you to. New event scopes do not apply to the old install.

Do not subscribe to `message.channels`. The bot only treats direct messages and @mentions as questions. Other channel traffic is ignored, and subscribing to it would send those messages to the API anyway.

---

## 10. Invite the bot and try it

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
| Slack will not save the request URL | The API is running, both secrets are set, the URL is `https://…/slack/events`, and the tunnel or Cloud Run service is up |
| `POST /slack/events` returns 503 | `SLACK_BOT_TOKEN` or `SLACK_SIGNING_SECRET` was empty when the process started |
| Slack says the command is unknown | The command was not created, or the name does not match the table in section 8 |
| `/forecast` works, an @mention does nothing | `app_mention` is not subscribed, the app was not reinstalled, or the bot was not invited to the channel |
| A direct message does nothing | **Messages Tab** is off, or `message.im` is not subscribed |
| The mention replies with the "AI agent is not configured" text | Set `OPENROUTER_API_KEY` and restart the API |
