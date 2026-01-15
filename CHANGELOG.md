# Changelog

All notable changes to this project.

---

## [2.0.0] - 2026-01-11

### 🎉 Major Refactoring Release

Complete architectural refactoring from monolithic agent files to a modular package structure with shared utilities.

### Added

- **BaseAgent Class** (`src/linkedin_agent/agents/base_agent.py`)
  - Abstract base class for all agents
  - Shared browser management, logging, config, audio, Gemini, and history
  - Lifecycle hooks: `on_start`, `on_complete`, `on_error`
  - Debug screenshot and HTML capture utilities
  - Run metrics tracking with `record_action()` and `record_error()`

- **Unified CLI** (`src/linkedin_agent/cli.py`)
  - Single entry point for all agents
  - Options: `--config`, `--headless`, `--debug`
  - Commands: `outreach`, `comment`, `engagement`, `notification`, `search`, `withdraw`

- **BrowserManager** (`src/linkedin_agent/utils/browser.py`)
  - Chrome launch with remote debugging
  - CDP connection management
  - Chat popup handling
  - PID detection and cleanup

- **AudioManager** (`src/linkedin_agent/utils/audio.py`)
  - Multi-tone ready sound (C5→E5→G5→C6)
  - Victory fanfare complete sound
  - Laptop speaker detection
  - Windows toast notifications

- **GeminiClient** (`src/linkedin_agent/utils/gemini.py`)
  - Unified Gemini API wrapper
  - `generate()` method for simple text generation
  - `classify_text()` for categorization
  - `analyze_screenshot()` for vision tasks
  - Legal professional detection

- **Documentation**
  - `docs/API.md` - Comprehensive API reference
  - `docs/AGENTS.md` - Detailed agent documentation
  - Updated README with CLI usage and architecture

### Changed

- **All agents now inherit from BaseAgent**
  - `OutreachAgent` (3023 → ~550 lines, 82% reduction)
  - `CommentAgent` (2632 → ~700 lines, 73% reduction)  
  - `NotificationAgent` (1520 → ~480 lines, 68% reduction)
  - `SearchAgent` (1484 → ~550 lines, 63% reduction)
  - `EngagementAgent` (1171 → ~550 lines, 53% reduction)

- **Package Structure**
  - Agents moved to `src/linkedin_agent/agents/`
  - Utilities moved to `src/linkedin_agent/utils/`
  - Core moved to `src/linkedin_agent/core/`
  - Templates moved to `src/linkedin_agent/templates/`

- **Data Organization**
  - History files now in `data/` directory
  - Log files now in `logs/` directory
  - Debug artifacts now in `debug/` directory

### Removed

- Duplicate browser launch code from each agent (~100 lines each)
- Duplicate logging code from each agent (~25 lines each)
- Duplicate history management from each agent (~30 lines each)
- Duplicate sound/notification code from each agent (~60 lines each)
- Duplicate Gemini client initialization (~20 lines each)

### Fixed

- Consistent error handling across all agents
- Proper async resource cleanup
- Atomic file saves for history

---

## [1.x] - Previous Versions

See git history for changes prior to 2.0.0.
