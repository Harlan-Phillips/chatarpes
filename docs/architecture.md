# ChatARPES Architecture

## Data Flow

```
User uploads .pxt files + types message
         |
         v
   React Frontend
   (chat UI, file upload, plot display)
         |
         v
   FastAPI Orchestrator
   (LLM routing, tool dispatch, session state)
         |
    +----+----+
    |         |
    v         v
  LLM      Analysis Engine
  (intent   (PyARPES, xarray,
  parsing,   matplotlib)
  Q&A)        |
    |         v
    v      .pxt loading,
  Knowledge  differentials,
  Store      plot generation
  (materials
  DB + RAG)
         |
         v
   Response: plot image + explanation
```

## LLM Options

| | Haiku 4.5 (recommended) | Sonnet 4.6 | Local Llama |
|---|---|---|---|
| Monthly | ~$1-5 | ~$5-15 | $0 (lab GPU) |
| Quality | Great for tools | Best reasoning | Weakest |
| Privacy | Data to API* | Data to API* | Full local |

*With tool-based architecture, raw .pxt data stays server-side. Only text goes to API.

## Open Questions (for lab lead)

1. API access: Do we have Anthropic tokens or only chatbot access?
2. Berkeley Lab AI: What's available? API keys? Hosted models?
3. Hosting: Lab server or cloud VM?
4. Auth: Google OAuth recommended, but need confirmation
