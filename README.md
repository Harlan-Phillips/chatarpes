# ChatARPES

A web-based AI assistant for ARPES researchers. Upload `.pxt` files, generate publication-quality plots, perform automated pump-probe comparisons, and ask natural language questions about materials and TR-ARPES concepts.

## Target Users

ARPES researchers from graduate students to PIs. Primary: Harmony Lab / Lanzara Group. Designed for the broader ARPES community.

## Architecture

```
Frontend (React + Tailwind)  -->  Orchestrator (FastAPI)  -->  Analysis Engine (PyARPES, xarray, matplotlib)
                                       |
                                  LLM Provider (Claude Haiku 4.5 recommended for v1)
                                       |
                                  Knowledge Store (JSON + optional vector DB)
```

## Core Features

1. **Plot Generation** - Band structure plots, differential maps, customization via chat, PNG/SVG export
2. **Pump-Probe Comparison** - Two-file differential workflow with metadata extraction
3. **Material Property Lookup** - Built-in database + RAG-enhanced answers
4. **Natural Language Q&A** - Concept explanations, troubleshooting, literature pointers

## Setup

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## Cost Estimate (50 sessions/day)

| | Haiku 4.5 | Sonnet 4.6 | Local (Llama) |
|---|---|---|---|
| Monthly cost | ~$3.60 | ~$10.80 | $0 (lab GPU) |
| With caching | ~$1-2/mo | ~$5-8/mo | N/A |
| Hosting | $0-12/mo | $0-12/mo | $0 (lab) |

## Items Needed from Lab Lead

See [`docs/placeholders/NEEDED_FROM_LAB.md`](docs/placeholders/NEEDED_FROM_LAB.md) for the full checklist of materials, data, and decisions needed to move forward.

## Laser Configuration

System uses a **1030nm Carbide laser** (not the setup paper default). See `docs/placeholders/equipment_specs.md`.

## Future Roadmap

- Manuals and manipulator documentation integration
- Method generation for other labs to build custom chatbots
- Record-keeping / documentation system for lab chatbot creation
