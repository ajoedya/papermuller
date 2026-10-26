# Run Papermuller on a laptop

The working folder is the extracted `papermuller` project directory containing
`app.py`, `requirements.txt`, and `env.example`. It is not a single PDF or Word
file. PDFs are added through **Topic & sources** once the app is running.

Open that folder in your local editor or terminal. A cloud workspace path such as
`/workspace/papermuller` belongs to the cloud machine; it is not a folder on your
laptop. A source archive or Git clone must first be downloaded to the laptop.
Use the latest `main` checkout or source archive to include the full-text,
editorial, and Windows launcher updates.

## Windows

Install Python 3.11 or newer and enable Python on PATH. Extract the project into
a folder such as `C:\Users\YourName\Documents\papermuller`. Then:

1. Double-click **Setup.bat** once. It creates a local virtual environment and
   installs the runtime packages without administrator privileges. Internet is
   required. Existing `.env`, PDFs and projects are preserved.
2. Double-click **Start.bat**. It uses that virtual environment and opens the
   app in your browser. If setup is missing, it invokes Setup.bat automatically.
3. Keep the terminal window open while the app is running. The address printed
   there is on your own laptop; this is a local application, not a hosted site.
4. In **Settings**, turn **Demo mode** off and enter your OpenRouter API key
   and OpenAlex API key where needed. Save and test the connections. Never send
   API keys in chat or commit them to Git.
5. Under **Topic & sources**, select local PDF files or enter a research topic.
   AI, discovery, DOI checks, and OA downloads use the Internet. `projects/` and
   `library/` remain in this project folder on your laptop.

Extract the whole ZIP before running the scripts. Do not run directly inside
Windows Explorer's ZIP view. If Windows blocks a downloaded script, inspect its
contents and use the trusted extracted copy; you do not need to disable antivirus
or change PowerShell execution policy. The project path can contain spaces.

The launchers are Windows batch scripts. They were inspected and packaged from a
Linux cloud machine; actual double-click execution on Windows still needs to be
verified on a Windows machine. Equivalent Python commands were tested here.

## macOS or Linux

Install Python 3.11 or newer, then open a terminal in the project folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
[ -e .env ] || cp env.example .env
.venv/bin/python app.py
```

The first dependency installation needs Internet access. Open the loopback address
printed by the server in your laptop's browser. Stop the server with Ctrl+C.

## Local application versus fully offline AI

| Mode | Works with current code? | Internet requirements |
| --- | --- | --- |
| Offline demo | Yes, after dependencies are installed | None for the scripted demo |
| Local app with OpenRouter | Yes | AI requests, paper discovery, DOI checks, and OA PDF downloads |
| Actual local AI with uploaded PDFs | Not yet | Requires a local-model backend and a local-only research path |

`DEMO_MODE=true` uses fictional, scripted responses. It is not an installed local
AI model. Turning demo mode off currently selects OpenRouter, which needs Internet
access and a key. Ollama/LM Studio integration is not implemented in the current
code. Installing one of those tools alone does not connect it to Papermuller.

For genuinely offline research, model weights and Python dependencies must be
prepared in advance. The workflow must use local PDFs and local metadata instead
of calling OpenAlex/Crossref. Appropriate model size depends on RAM, GPU memory,
and the laptop's operating system. A cloud-produced Python virtual environment
must not be copied as a portable Windows/macOS installation.

## Update an existing Windows copy

If the project folder contains a `.git` directory and has no unfinished local
changes, open PowerShell in that folder and run:

```powershell
git pull --ff-only origin main
.\Setup.bat
.\Start.bat
```

A folder extracted from GitHub's ZIP does not contain Git history, so `git pull`
will not update it. Download the latest ZIP, extract it into a new folder, close
the old running app, then copy your `.env`, `projects`, and `library` from the old
folder into the new one. Keep the old folder until your data is verified. Run
Setup.bat and Start.bat from the new folder. Do not copy the old `.venv`; let
Setup.bat create an environment matching the updated dependencies.
