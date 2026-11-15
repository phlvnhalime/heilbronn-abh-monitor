# Heilbronn ABH appointment checker

This project checks the Heilbronn Ausländerbehörde (ABH) booking page for an earlier residence-permit extension appointment (`Verlängerung Aufenthaltserlaubnis`). When a new slot is earlier than the one already saved, it sends a Telegram message.

> [!IMPORTANT]
> This tool is intended for personal use and only monitors publicly available appointment information.
>
> - It does not automatically book appointments.
> - Please respect the website's terms of use.
> - Avoid excessive requests.

The page labels the checker clicks stay in German, because those strings are part of the website. Log lines, errors, and the Telegram text are in English.

## What the checker does

1. Opens [etermin Heilbronn ABH](https://www.etermin.net/qtermin-stadtheilbronn-abh) with Playwright.
2. Selects **Aufenthaltserlaubnis**, then the residence-permit extension service.
3. Reads visible appointment days and time ranges.
4. Compares the earliest slot with `appointment_state.json`.
5. Sends a Telegram message only when that slot is both earlier and new.
6. Writes the latest slots back to `appointment_state.json`.

The first successful run only saves state. It does not send a message.

## GitHub Actions

Two workflows live in `.github/workflows/`.

| Workflow | File | When it runs |
| --- | --- | --- |
| Check Heilbronn ABH appointments | `check.yml` | Every hour at minute 7 and minute 37, or manually |
| Schedule Trigger Test | `schedule-test.yml` | Every 5 minutes, or manually |

GitHub schedules use UTC. `7,37 * * * *` means 07 and 37 minutes past every hour, all day.

### Secrets

The check job reads these repository secrets. It does not use a `.env` file in Actions.

| Secret | Purpose |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Chat that should receive the alert |

Add them under **Settings → Secrets and variables → Actions → New repository secret**.

### Check workflow steps

The job runs on `ubuntu-24.04` and stops after 12 minutes. Only one check runs at a time.

1. **Checkout `main`**  
   `actions/checkout@v4` clones `main` and keeps the token so a later step can push.

2. **Set up Python 3.12**  
   `actions/setup-python@v5` installs Python 3.12.

3. **Install dependencies**  
   - Upgrade pip.  
   - Install `playwright`, `requests`, and `python-dotenv` from `requirements.txt`.  
   - Install Chromium and the system libraries Playwright needs:  
     `python -m playwright install --with-deps chromium`

4. **Check appointments**  
   Runs `python appointment_checker.py` with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from secrets.  
   The script prints one of these lines:
   - `No verifiable time slots found; state was not changed.`
   - `First check: saving the initial state, no message sent.`
   - `Telegram notification sent.`
   - `No earlier new appointment. Notification not sent.`

5. **Save appointment state**  
   If `appointment_state.json` changed:
   - Sets the commit author to `github-actions[bot]`.
   - Commits with `Update appointment state [skip ci]`.
   - Pushes to `main`.

   `[skip ci]` keeps that commit from starting another workflow run. The file is listed in `.gitignore`, so this step adds it with `git add -f`.

The job needs **contents: write** so that push is allowed. On a new repository, also enable **Settings → Actions → General → Workflow permissions → Read and write permissions**.

### Run it by hand

1. Open the **Actions** tab.
2. Choose **Check Heilbronn ABH appointments**.
3. Click **Run workflow** and select `main`.

The schedule test workflow only prints the UTC time. Use it to confirm that GitHub is firing scheduled jobs.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Create a `.env` file in the project root. It is gitignored.

```bash
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_CHAT_ID=your-chat-id
```

Then run:

```bash
python appointment_checker.py
```
