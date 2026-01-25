# Marlo Inbox

An AI-powered email and calendar assistant built with [Marlo](https://marshmallo.ai). Marlo Inbox demonstrates how to build a production-ready agent that manages Gmail and Google Calendar on behalf of users, while continuously learning from interactions.

## What It Does

Marlo Inbox is an agent that can:

- Read, search, and summarize emails
- Draft and send email replies
- View calendar events and check availability
- Schedule meetings and manage invites
- Learn from past interactions to improve over time

## Architecture

```
+-------------+     +-------------+     +-------------+
|   Client    |---->|  LangGraph  |---->|   Marlo     |
|             |     |   Server    |     |  Platform   |
+-------------+     +------+------+     +-------------+
                           |
              +------------+------------+
              |                         |
        +-----v-----+            +-----v-----+
        |  Gmail    |            |  Google   |
        |   API     |            | Calendar  |
        +-----------+            +-----------+
```

## Prerequisites

Before you begin, ensure you have:
- A [Google Cloud](https://console.cloud.google.com) account
- A [Marlo](https://marshmallo.ai) account
- An [OpenAI](https://platform.openai.com) API key

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Marshmallo-AI/marlo-inbox.git
cd marlo-inbox
```

### 2. Configure Google Cloud

Google Cloud provides the APIs for Gmail and Calendar access.

#### 2.1 Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com).
2. Click the project dropdown at the top and select **New Project**.
3. Enter a project name (e.g., `marlo-inbox`) and click **Create**.
4. Wait for the project to be created, then select it.

#### 2.2 Configure OAuth Consent Screen

1. Navigate to **APIs & Services** > **OAuth consent screen**.
2. Select **External** and click **Create**.
3. Fill in the required fields:
   - **App name**: `Marlo Inbox`
   - **User support email**: Your email address
   - **Developer contact email**: Your email address
4. Click **Save and Continue**.

#### 2.3 Add Scopes

1. On the Scopes page, click **Add or Remove Scopes**.
2. Add the following scopes:
   ```
   email
   profile
   openid
   https://www.googleapis.com/auth/gmail.modify
   https://www.googleapis.com/auth/gmail.readonly
   https://www.googleapis.com/auth/gmail.send
   https://www.googleapis.com/auth/calendar
   https://www.googleapis.com/auth/calendar.events
   ```
3. Click **Update**, then **Save and Continue**.

#### 2.4 Add Test Users

While your app is in testing mode, only approved test users can authenticate.

1. On the Test Users page, click **Add Users**.
2. Enter the email addresses of users who will test the application.
3. Click **Save and Continue**.

#### 2.5 Create OAuth Credentials

1. Navigate to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Select **Web application** as the application type.
4. Enter a name (e.g., `marlo-inbox`).
5. Under **Authorized redirect URIs**, add:
   ```
   http://localhost:5173/api/auth/callback
   ```
6. Click **Create**.
7. Copy the **Client ID** and **Client Secret**.

#### 2.6 Enable APIs

1. Navigate to **APIs & Services** > **Library**.
2. Search for and enable the following APIs:
   - **Gmail API**
   - **Google Calendar API**

### 3. Configure Marlo

Marlo provides the learning infrastructure that helps the agent improve over time.

1. Go to [marshmallo.ai](https://marshmallo.ai) and create an account.
2. Create an organization and a project.
3. Navigate to **Settings** > **Project** and copy your API key.

### 4. Set Up Environment Variables

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Open `.env` and fill in the values:

   ```bash
   # App Configuration
   APP_NAME="marlo-inbox"
   APP_BASE_URL="http://localhost:5173"
   SESSION_SECRET="your-random-secret-string"

   # Google OAuth (from Step 2.5)
   GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
   GOOGLE_CLIENT_SECRET="your-client-secret"

   # OpenAI
   OPENAI_API_KEY="sk-..."

   # Marlo
   MARLO_API_KEY="your-marlo-api-key"
   ```

### 5. Install and Run

```bash
# Install dependencies
pip install -e .
cd web && npm install && cd ..

# Run the full stack
make dev
```

This starts:
- FastAPI backend on `http://localhost:8000`
- LangGraph server on `http://localhost:2024`
- React frontend on `http://localhost:5173`

## Usage

1. Open `http://localhost:5173` in your browser
2. Click **Login with Google** to authenticate
3. Start chatting with the agent to manage your emails and calendar

### Example Prompts

- "Show me my recent emails"
- "Search for emails from john@example.com"
- "Draft a reply to the last email saying I'll get back to them tomorrow"
- "What's on my calendar this week?"
- "Schedule a meeting with sarah@example.com tomorrow at 2pm"
- "Find a free slot for a 30-minute meeting next Monday"

## Available Tools

| Tool | Description |
|------|-------------|
| `list_emails` | List recent emails from the inbox |
| `get_email` | Get full content of a specific email |
| `search_emails` | Search emails using Gmail query syntax |
| `draft_reply` | Generate a draft reply to an email |
| `send_email` | Send an email or reply to a thread |
| `get_schedule` | Get calendar events for a date range |
| `check_availability` | Check if a time slot is free |
| `find_free_slots` | Find available meeting times |
| `create_event` | Create a calendar event |
| `delete_event` | Delete a calendar event |

## How Learning Works

Marlo Inbox integrates with the Marlo platform to continuously improve:

1. **Capture**: Every task execution is recorded, including inputs, outputs, tool calls, and LLM interactions.
2. **Evaluate**: Task outcomes are automatically scored based on success criteria.
3. **Learn**: Failures and successes are converted into learnings that describe what worked and what to avoid.
4. **Apply**: Active learnings are injected into the agent's context, improving future responses.

View your agent's learnings and performance in the [Marlo Dashboard](https://marshmallo.ai).

## Troubleshooting

### "redirect_uri_mismatch" Error

Ensure the redirect URI in Google Cloud Console exactly matches:
```
http://localhost:5173/api/auth/callback
```

### "Access blocked" Error

Make sure your email is added as a test user in the OAuth consent screen settings.

### "Insufficient scopes" Error

Verify that all required scopes are added in the Google Cloud Console OAuth consent screen.

## Links

- [Marlo Documentation](https://docs.marshmallo.ai)
- [Google Cloud Console](https://console.cloud.google.com)

## License

MIT
