# DQP Local Workspace

Last verified: 2026-09-20

## Windows laptop clone

PowerShell discovered the local DQP repository at:

`C:\Users\tomag\dev\dividend-capture-scanner`

Use this as the preferred laptop workspace for Cursor/Codex/local repository audits.

This path is **not** the production runtime.

Production runtime remains:

`/data/data/com.termux/files/home/dividend-capture-scanner`

Obsidian vault remains:

`D:\Obsidian\Engineering`

Before making local edits, always verify the laptop clone with `git remote -v`, `git branch --show-current`, `git rev-parse HEAD`, and `git status --short` rather than assuming it matches GitHub or the Termux runtime.
