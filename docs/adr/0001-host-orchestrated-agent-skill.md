# Host-Orchestrated Agent Skill Over Standalone LLM CLI

PreFlight is packaged as a native Agent Skill (`SKILL.md` plus deterministic Python helper scripts for GitHub API scouting and HTML Blueprint generation) rather than a standalone `gemini-2.5-flash` CLI loop. When running inside an AI coding environment (Antigravity, Claude Code, Cursor), the host agent already provides the reasoning loop, conversation context, and subagent orchestration; embedding a second LLM client inside a CLI script would duplicate API keys, split conversation history, and prevent native access to workspace files.
