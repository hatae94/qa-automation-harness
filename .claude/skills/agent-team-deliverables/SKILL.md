---
name: agent-team-deliverables
description: Use when assembling agent teams for discussion, brainstorming, review, or any multi-agent collaborative task - ensures meeting notes and final reports are always produced as MD files and delivered to the user
---

# Agent Team Deliverables

## Overview

Every agent team discussion or collaborative task MUST produce two deliverables: a **meeting notes** document and a **final report** document, both as Markdown files.

## When to Use

- Assembling agent teams for discussion or brainstorming
- Running multi-agent reviews or critiques
- Any task involving simulated team roles or perspectives
- User requests "discussion", "review", "brainstorm", or "team" work

## Required Deliverables

### 1. Meeting Notes (회의록)

**File:** `docs/plans/YYYY-MM-DD-<topic>-meeting-notes.md`

**Structure:**
- Participants and roles
- Background and objectives
- Discussion points with each participant's perspective
- Key debates, disagreements, and resolutions
- Action items and next steps

### 2. Final Report (최종 보고서)

**File:** `docs/plans/YYYY-MM-DD-<topic>-final-report.md`

**Structure:**
- Executive summary
- Detailed analysis with diagrams (mermaid)
- Recommendations with rationale
- Risk assessment
- Implementation roadmap (if applicable)
- Appendices with concrete examples

## Delivery Process

After writing both files:

1. Copy files to `/tmp/openclaw/` (media access allowed directory)
2. Send via Telegram using:
   ```bash
   node dist/entry.js message send --channel telegram --target <chat-id> \
     --message "<title>" --media /tmp/openclaw/<filename>
   ```
3. Confirm delivery to user

## Versioning

When a review/critique cycle produces improved versions, append `-v2`, `-v3` etc. to filenames. Always send the latest version.

## Common Mistakes

- Forgetting to copy files to `/tmp/openclaw/` before sending (LocalMediaAccessError)
- Using `--to` instead of `--target` flag
- Using relative paths instead of absolute paths for `--media`
