# cewmail

A small, local automatic-mailing tool: pick a category, describe the context, get a
few AI-drafted email options, edit, and send -- plus a live inbox view so you can
reply to received mail with the same generate/edit/send flow.

Runs entirely on `127.0.0.1` (localhost only). No database, no accounts, single user.

## Features

- Pick an email category (costing, follow-up, enquiry, or any you add) and describe
  the context -- get 3 drafted options from Google Gemini (free tier), with OpenAI as
  an automatic silent fallback if Gemini fails.
- Add new categories/templates from the UI itself.
- Edit the chosen draft before sending; attach files.
- Sends via Gmail SMTP.
- Inbox tab shows your ~25 most recent emails (via IMAP); Reply on any of them
  drafts a proper threaded reply (In-Reply-To/References headers) using the
  original email as context.

## Mac / local dev setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you don't have it.
2. `uv sync` -- creates `.venv/` and installs all dependencies.
3. `cp .env.example .env` and fill in real values (see below).
4. `uv run app.py`
5. Open http://127.0.0.1:5000

## Getting a Gemini API key

Free tier, primary LLM backend. Get one at https://aistudio.google.com/apikey and
put it in `.env` as `GEMINI_API_KEY`.

## Getting an OpenAI API key (fallback only)

Only used automatically when Gemini fails (rate limit, outage, bad key). No free
tier -- usage-based, but since it's only a fallback, normal day-to-day use of this
tool shouldn't incur any OpenAI cost. Get a key at https://platform.openai.com/api-keys
and put it in `.env` as `OPENAI_API_KEY`. If you don't set one, the app just surfaces
Gemini's error directly when Gemini fails.

## Getting a Gmail app password

Gmail SMTP/IMAP require an **app password**, not your normal account password:

1. Turn on 2-Step Verification on your Google account (Security settings) -- the
   App Passwords option is hidden until this is on.
2. Google Account -> Security -> App Passwords -> generate one for "Mail".
3. Put your Gmail address and that 16-character password in `.env` as
   `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD`. The same app password is used for both
   sending (SMTP) and reading the inbox (IMAP).

## Adding/editing categories

Either use "+ Add category" in the app, or hand-edit/add a `.txt` file directly
under `email_templates/` -- the filename (without `.txt`) becomes the category name.
Each file is plain-text instructions describing the tone/structure for that kind
of email; it's fed to the LLM alongside your per-email context, not a fill-in-the-blank
mail-merge template.

## Windows deployment (via nssm)

One-time setup on the Windows machine:

1. Clone this repo there, then `git remote add origin <your-repo-url>` (needed
   later for updates).
2. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) on Windows.
3. `uv sync` in the project folder.
4. `cp .env.example .env` and fill it in (same values as above).
5. Download [nssm](https://nssm.cc/download); put `nssm.exe` on PATH or in
   `deploy\tools\nssm.exe`.
6. Run `deploy\install_service.bat` from an elevated Command Prompt.

The app then runs as a Windows service named `cewmail`, auto-starting on boot,
reachable at http://127.0.0.1:5000 on that machine.

## Updating the Windows deployment

After pushing new commits to your remote, on the Windows machine, from an
**elevated (Administrator) Command Prompt** (restarting a Windows service
always needs admin rights -- an unelevated prompt fails on the final step
with "OpenService() is denied"), run:

```
deploy\update.bat
```

This does `git pull` + `uv sync` + restarts the `cewmail` service. It aborts
without restarting if `git pull` or `uv sync` fails, so a broken pull never
takes down the running service.

## Troubleshooting

- **Service won't start**: check `logs\service.err.log` in the project folder.
- **"OpenService() is denied"** (from `install_service.bat` or `update.bat`):
  the Command Prompt isn't elevated -- right-click it and choose "Run as
  administrator", then re-run the script.
- **SMTP/IMAP auth errors**: regenerate the Gmail app password and update `.env`.
- **"Could not generate drafts"**: check `GEMINI_API_KEY` (and `OPENAI_API_KEY` if
  you want the fallback to work); check quota/rate limits on whichever backend the
  error mentions.
- **Inbox fails to load**: make sure IMAP is enabled on the Gmail account (Gmail
  Settings -> Forwarding and POP/IMAP -> Enable IMAP) -- it's on by default for
  most accounts.
- **nssm install issues**: make sure all paths are correct and that `.venv\` exists
  (run `uv sync` first) -- `install_service.bat` checks for this and will tell you
  if something's missing.
