# marlo-inbox

AI email & calendar assistant powered by Marlo and Auth0.

An open-source LangGraph agent that manages your Gmail inbox and Google Calendar through natural conversation.

## Features

- **Email Management**: List, read, search, draft, and send emails
- **Calendar Management**: View schedule, check availability, create events
- **Natural Conversation**: Just chat to manage your inbox
- **Secure Authentication**: Auth0 handles login and Google token management
- **Observable AI**: Marlo tracks agent behavior and enables learning

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   LangGraph Studio                   │
└─────────────────────────┬───────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────┐
│                      FastAPI                         │
│  • Auth0 session management                          │
│  • LangGraph proxy                                   │
└─────────────────────────┬───────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────┐
│                  LangGraph Agent                     │
│  • 5 Email tools (Gmail API)                         │
│  • 5 Calendar tools (Google Calendar API)            │
└──────────┬──────────────┬───────────────┬───────────┘
           │              │               │
    ┌──────▼──────┐ ┌─────▼─────┐ ┌───────▼───────┐
    │    Auth0    │ │  Google   │ │     Marlo     │
    │ Token Vault │ │   APIs    │ │  Observability│
    └─────────────┘ └───────────┘ └───────────────┘
```

## Prerequisites

- Python 3.11+
- Auth0 account with Google social connection
- Google Cloud project with Gmail and Calendar APIs enabled
- OpenAI API key
- Marlo API key

## Setup

1. Clone and install dependencies:
```bash
git clone https://github.com/marlo-ai/marlo-inbox.git
cd marlo-inbox
uv sync
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Run the agent:
```bash
uv run langgraph dev
```

## Environment Variables

See `.env.example` for all required configuration.

## Documentation

- [Setup Guide](docs/setup.md)
- [Auth0 Configuration](docs/auth0-setup.md)
- [Google Cloud Setup](docs/google-setup.md)

## License

MIT
