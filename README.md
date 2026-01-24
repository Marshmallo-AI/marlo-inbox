# Marlo Inbox

An AI-powered email and calendar assistant built with [Auth0](https://auth0.com) and [Marlo](https://marshmallo.ai). Marlo Inbox demonstrates how to build a production-ready agent that manages Gmail and Google Calendar on behalf of users, while continuously learning from interactions.

## What It Does

Marlo Inbox is an agent that can:

- Read, search, and summarize emails
- Draft and send email replies
- View calendar events and check availability
- Schedule meetings and manage invites
- Learn from past interactions to improve over time

The agent uses Auth0 for secure user authentication and Token Vault for federated access to Google APIs, ensuring user credentials are never exposed to the application.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│  LangGraph  │────▶│   Marlo     │
│             │     │   Server    │     │  Platform   │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │   Auth0     │
                    │ Token Vault │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
        ┌─────▼─────┐            ┌─────▼─────┐
        │  Gmail    │            │  Google   │
        │   API     │            │ Calendar  │
        └───────────┘            └───────────┘
```

## Prerequisites

Before you begin, ensure you have:
- An [Auth0](https://auth0.com) account
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

Google Cloud provides the APIs for Gmail and Calendar access. You need to create OAuth credentials that Auth0 will use to authenticate users.

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

![OAuth Consent Screen](./docs/images/google-oauth-consent.png)

#### 2.3 Add Scopes

1. On the Scopes page, click **Add or Remove Scopes**.
2. Add the following scopes:
   ```
   email
   profile
   openid
   https://www.googleapis.com/auth/gmail.modify
   https://www.googleapis.com/auth/gmail.readonly
   https://www.googleapis.com/auth/calendar
   https://www.googleapis.com/auth/calendar.events
   ```
3. Click **Update**, then **Save and Continue**.

![Google Scopes](./docs/images/google-scopes.png)

#### 2.4 Add Test Users

While your app is in testing mode, only approved test users can authenticate.

1. On the Test Users page, click **Add Users**.
2. Enter the email addresses of users who will test the application.
3. Click **Save and Continue**.

#### 2.5 Create OAuth Credentials

1. Navigate to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Select **Web application** as the application type.
4. Enter a name (e.g., `marlo-inbox-auth0`).
5. Under **Authorized redirect URIs**, add:
   ```
   https://YOUR_AUTH0_DOMAIN/login/callback
   ```
   Replace `YOUR_AUTH0_DOMAIN` with your Auth0 domain (e.g., `dev-abc123.us.auth0.com`).
6. Click **Create**.
7. Copy the **Client ID** and **Client Secret**. You will need these for Auth0 configuration.

![Google Credentials](./docs/images/google-credentials.png)

#### 2.6 Enable APIs

1. Navigate to **APIs & Services** > **Library**.
2. Search for and enable the following APIs:
   - **Gmail API**
   - **Google Calendar API**

### 3. Configure Auth0

Auth0 handles user authentication and securely stores Google tokens using Token Vault.

#### 3.1 Create an Auth0 Application

1. Log in to your [Auth0 Dashboard](https://manage.auth0.com).
2. Navigate to **Applications** > **Applications**.
3. Click **Create Application**.
4. Enter a name (e.g., `marlo-inbox`) and select **Single Page Application**.
5. Click **Create**.
6. In the application settings, note your **Domain**, **Client ID**, and **Client Secret**.

![Auth0 Application](./docs/images/auth0-application.png)

#### 3.2 Create an API

1. Navigate to **Applications** > **APIs**.
2. Click **Create API**.
3. Fill in the fields:
   - **Name**: `marlo-inbox-api`
   - **Identifier**: `https://marlo-inbox` (this becomes your `AUTH0_AUDIENCE`)
   - **Signing Algorithm**: RS256
4. Click **Create**.

![Auth0 API](./docs/images/auth0-api.png)

#### 3.3 Configure Google Social Connection

1. Navigate to **Authentication** > **Social**.
2. Find **Google** and click to configure (or click **Create Connection** if not present).
3. Enter the **Client ID** and **Client Secret** from Google Cloud (Step 2.5).
4. Under **Permissions**, add the following scopes:
   ```
   email
   profile
   https://www.googleapis.com/auth/gmail.modify
   https://www.googleapis.com/auth/gmail.readonly
   https://www.googleapis.com/auth/calendar
   https://www.googleapis.com/auth/calendar.events
   ```
5. For **Purpose**, select **Authentication and Connected Accounts for Token Vault**.
6. Click **Save**.

![Auth0 Google Connection](./docs/images/auth0-google-connection.png)

#### 3.4 Create Machine-to-Machine Application

Token Vault requires a Machine-to-Machine (M2M) application to retrieve user tokens.

1. Navigate to **Applications** > **Applications**.
2. Click **Create Application**.
3. Enter a name (e.g., `marlo-inbox-m2m`) and select **Machine to Machine**.
4. Click **Create**.
5. When prompted to authorize an API, select **Auth0 Management API**.
6. Grant the following permissions:
   - `read:users`
   - `read:user_idp_tokens`
7. Click **Authorize**.
8. In the application settings, go to **Advanced Settings** > **Grant Types**.
9. Enable `urn:ietf:params:oauth:grant-type:token-exchange`.
10. Note the **Client ID** and **Client Secret** for this M2M application.

![Auth0 M2M App](./docs/images/auth0-m2m.png)

### 4. Configure Marlo

Marlo provides the learning infrastructure that helps the agent improve over time.

1. Go to [marshmallo.ai](https://marshmallo.ai) and create an account.
2. Create an organization and a project.
3. Navigate to **Settings** > **Project** and copy your API key.

### 5. Set Up Environment Variables

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Open `.env` and fill in the values:

   ```bash
   # App Configuration
   APP_NAME="marlo-inbox"
   APP_BASE_URL="http://localhost:5173"

   # Auth0 - From your Auth0 Application (Step 3.1)
   AUTH0_DOMAIN="your-tenant.us.auth0.com"
   AUTH0_CLIENT_ID="your-client-id"
   AUTH0_CLIENT_SECRET="your-client-secret"
   AUTH0_AUDIENCE="https://marlo-inbox"

   # Auth0 M2M - From your M2M Application (Step 3.4)
   AUTH0_CUSTOM_API_CLIENT_ID="your-m2m-client-id"
   AUTH0_CUSTOM_API_CLIENT_SECRET="your-m2m-client-secret"

   # OpenAI
   OPENAI_API_KEY="sk-..."

   # Marlo
   MARLO_API_KEY="your-marlo-api-key"
   ```

### 6. Install and Run

#### TypeScript Version

```bash
cd ts-inbox
npm install
npm run dev
```

The LangGraph server starts at `http://localhost:54367`.

#### Python Version

```bash
cd py-inbox
pip install -e .
langgraph dev
```

## Usage

Once the server is running, LangGraph Studio opens automatically in your browser. This provides a visual interface to interact with the agent.

### Using LangGraph Studio

1. **Start a conversation**: Type your request in the chat input (e.g., "Show me my recent emails")
2. **Authenticate**: On first use, you'll be prompted to connect your Google account via Auth0
3. **Interact**: Continue chatting to manage emails and calendar

![LangGraph Studio](./docs/images/langgraph-studio.png)

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

### "Token Vault requires own keys" Error

This error appears when configuring the Google connection in Auth0. You must use your own Google OAuth credentials, not Auth0's default developer keys. Follow Step 2 to create credentials in Google Cloud Console.

### "Invalid redirect URI" Error

Ensure the redirect URI in Google Cloud Console exactly matches your Auth0 domain:
```
https://YOUR_AUTH0_DOMAIN/login/callback
```

### "Insufficient scopes" Error

Verify that all required scopes are added in both:
- Google Cloud Console OAuth consent screen
- Auth0 Google social connection settings

## Links

- [Marlo Documentation](https://docs.marshmallo.ai)
- [Auth0 Documentation](https://auth0.com/docs)
- [Google Cloud Console](https://console.cloud.google.com)

## License

MIT
