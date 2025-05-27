# Progress Reporting Improvements

This document describes the enhanced progress reporting system implemented in Dora.

## Overview

Previously, users had no visibility into what was happening during the 1-2 minute processing time. The system now provides:

- **Real-time progress updates** in Telegram chat
- **Detailed logging** for debugging and monitoring
- **Step-by-step visibility** into the processing pipeline

## Features

### 1. Progress Callback System

The main `process_city()` function now accepts an optional `progress_callback` parameter:

```python
async def process_city(
    city: str, 
    days_ahead: int = 14, 
    events_count: int = 10, 
    config: Optional[DoraConfig] = None, 
    progress_callback: Optional[callable] = None
):
```

The callback receives two parameters:
- `step`: A short identifier for the current step (e.g., "INITIALIZING", "STARTING_SEARCH")
- `details`: Detailed description of what's happening

### 2. Telegram Bot Live Updates

The Telegram bot now shows live progress updates during processing:

- 🔧 Setting up search system...
- 🤖 Preparing AI agents...
- ⚙️ Building processing tools...
- 🔍 Starting event discovery...
- 🎭 Finding and analyzing events...
- 📊 Processing and formatting results...
- ✅ Search completed!

### 3. Enhanced Logging

All processing steps now log at INFO level with `[PROGRESS]` tags:

```
[PROGRESS] INITIALIZING: Setting up OpenAI client and agents
[PROGRESS] CREATING_AGENTS: Setting up 10 event processing pipeline
[PROGRESS] STARTING_SEARCH: Searching for 10 events in San Francisco
```

### 4. API Call Visibility

Perplexity API calls now log:
- When requests start
- Request completion time
- Response size

```
[PERPLEXITY] Starting search query: San Francisco upcoming events next 2 weeks
[PERPLEXITY] Sending request to API...
[PERPLEXITY] Completed search in 2.45 seconds, received 3247 characters
```

### 5. Enhanced Trace Processor

The debug trace processor now outputs to both logs and console:

```
🔍 Starting: ProcessCity:San Francisco
   City: San Francisco, Events: 10
⚡ Starting step: AgentCall
✅ Completed step: AgentCall
✅ Completed: ProcessCity:San Francisco
   Duration: 45.23s, Events found: 8
```

### 6. Agent Step Announcements

The orchestrator agent now announces each step it performs:

- "Finding events in [city]..."
- "Getting languages for [city]..."
- "Classifying event X of Y: [event name]..."
- "Creating notification combinations for all events..."
- "Generating all notifications..."

## Usage

### For CLI Usage

Enable debug logging to see all progress messages:

```bash
LOG_LEVEL=DEBUG uv run python -m dora --city "San Francisco"
```

### For Telegram Bot

Progress updates are automatically shown to users in real-time. No configuration needed.

### For API Integration

Pass a progress callback function:

```python
async def my_progress_callback(step: str, details: str):
    print(f"Progress: {step} - {details}")

results = await process_city(
    city="San Francisco",
    progress_callback=my_progress_callback
)
```

## Progress Steps

| Step | Description |
|------|-------------|
| `INITIALIZING` | Setting up OpenAI client and configuration |
| `CREATING_AGENTS` | Creating AI agents for event processing |
| `BUILDING_TOOLS` | Setting up agent tools and orchestrator |
| `STARTING_SEARCH` | Beginning event discovery process |
| `RUNNING_ORCHESTRATOR` | Executing the main processing pipeline |
| `PROCESSING_RESULTS` | Filtering and formatting results |
| `COMPLETED` | Processing finished successfully |

## Testing

Run the progress reporting test:

```bash
uv run python test_progress.py
```

This will test the progress callback system and verify all improvements are working.

## Benefits

1. **User Experience**: Users now see what's happening instead of waiting in silence
2. **Debugging**: Detailed logs help identify where issues occur
3. **Monitoring**: Progress tracking helps with performance analysis
4. **Transparency**: Clear visibility into the multi-step AI pipeline

## Future Enhancements

Potential improvements:
- Progress bars with percentage completion
- Estimated time remaining
- Real-time event count updates
- Webhook progress notifications for API users