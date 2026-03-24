# Items Needed from Lab Lead

Master checklist of everything needed to build out ChatARPES. Items marked with `[ ]` are outstanding.

---

## Papers & References

- [ ] **Setup paper** for the TR-ARPES system (NOTE: laser must be updated to 1030nm Carbide laser in any references)
- [ ] Key review papers on TR-ARPES technique (PDFs or DOIs)
- [ ] Papers covering HHG source details
- [ ] Relevant Harmony Lab publications for RAG corpus
- [ ] Textbook chapters or sections on ARPES fundamentals (for embedding)
- [ ] Any papers specific to materials commonly studied (1T-TaS2, Bi2Se3, TMDCs, etc.)

**Place PDFs in:** `knowledge/papers/`

---

## Sample Data

- [ ] **Sample .pxt files** for testing (at least one reference + one pumped scan)
  - Priority: Bi2Se3 test files first, then TaS2
- [ ] Example .pxt files that demonstrate edge cases (noisy data, misaligned scans, etc.)
- [ ] Confirmation of .pxt header format and what metadata fields are available

**Place .pxt files in:** `data/sample_pxt/`

---

## Material Database Info

- [ ] List of **20-30 materials** commonly studied in Harmony Lab with:
  - Chemical formula
  - Crystal structure / space group
  - Lattice constants (a, b, c)
  - Band gap
  - CDW transition temperature (if applicable)
  - Topological classification (if applicable)
  - Key references (DOIs)
- [ ] Any corrections or additions to this starter list:
  `1T-TaS2, graphene, Bi2Se3, WS2, WSe2, MoS2, MoSe2, ...`

---

## Equipment & Configuration

- [ ] **1030nm Carbide laser** specifications:
  - Pulse duration
  - Repetition rate
  - Power / pulse energy
  - Any other relevant parameters
- [ ] Hemispherical analyzer model and specs (Scienta model number, energy/angular resolution)
- [ ] Delay stage specifications (range, resolution)
- [ ] Cryostat / manipulator details
- [ ] Vacuum system overview
- [ ] Any other beamline or endstation details

**Place specs in:** `docs/placeholders/equipment_specs.md`

---

## Manuals & SOPs

- [ ] Equipment manuals (analyzer, laser, manipulator, etc.)
- [ ] Lab SOPs for running TR-ARPES experiments
- [ ] PyARPES-specific documentation or notebooks used in the lab
- [ ] Any existing Jupyter notebooks for TR-ARPES analysis (these will be wrapped into the analysis engine)

**Place in:** `knowledge/manuals/`

---

## Lab Website & Documentation

- [ ] Content from Harmony Lab website (About ARPES, Equipment pages)
- [ ] Any internal wiki or documentation pages
- [ ] Lab group photos or branding (for frontend, optional)

**Place in:** `knowledge/lab_docs/`

---

## Access & Authentication Decisions

- [ ] **LLM API access**: Do we have Anthropic API tokens, or only chatbot access? (affects architecture choice between Option A/B/C)
- [ ] **Berkeley AI access**: Confirm what Berkeley Lab provides (API keys? hosted models? chatbot-only?)
- [ ] **Auth method preference**: Google OAuth (@berkeley.edu), shared passphrase, or CalNet SSO?
- [ ] **Domain**: Can we get `chatarpes.berkeley.edu` or similar?
- [ ] **Hosting**: Lab server available, or need cloud VM?
- [ ] **Budget approval**: Confirm monthly budget for API + hosting (~$5-15/month for recommended setup)

---

## Future: Other Labs & Customization

- [ ] List of other labs that might adopt ChatARPES
- [ ] What would a "method for other labs" look like? (documentation? template repo? hosted service?)
- [ ] Requirements for record-keeping / docs system for custom chatbot creation
