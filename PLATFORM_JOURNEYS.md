# INHOUS Platform — Journeys, Access & Alerts

How the platform looks and behaves for each participant: what they can do, what
they can see, what is hidden from them, and when they get notified. Diagrams are
Mermaid — they render in Claude / GitHub / VS Code.

---

## 1. Roles

| Role | Who | INHOUS member? |
|------|-----|----------------|
| **broker** | INHOUS — runs the whole transaction | ✅ Yes (full visibility) |
| **vendor** | The seller | ❌ External |
| **agent** | Estate agent / negotiator | ❌ External |
| **vendor_solicitor** | Seller's solicitor | ❌ External |
| **buyer_solicitor** | Buyer's solicitor | ❌ External |
| **buyer** | The purchaser | ❌ External |
| **photographer** | Property photographer | ❌ External |
| **family_office** | Family-office observer | ❌ External |

**Golden rule:** only the **broker (INHOUS)** sees everyone's contact details and
all documents. External parties see what their role needs — and on the
Participants screen they see other people **by name only**.

---

## 2. End-to-end lifecycle

```mermaid
flowchart TD
  A[Broker onboards property and vendor] --> B[Vendor AML / KYC captured]
  B --> C[Valuations: up to 5 agents submit]
  C --> D[Vendor reviews valuation report]
  D --> E[Broker instructs selling agents]
  E --> F[Photographer invited and shoot booked]
  F --> G[Photos and floorplans uploaded]
  G --> H[Listing goes live - status active]
  H --> I[Agents book viewings]
  I --> J[Agents submit feedback - typed or voice]
  J --> K[Vendor reads feedback]
  I --> L[Agents submit offers + buyer PoF / AML]
  L --> M{Broker and vendor review}
  M -->|counter| L
  M -->|decline| L
  M -->|accept| N[Offer accepted - status under_offer]
  N --> O[Memorandum of sale sent to both solicitors]
  O --> P[Solicitors upload AML / KYC]
  P --> Q[Conveyancing]
  Q --> R[Introductions: cleaner, removals, designer, builder, gardener]
  R --> S[Completion - status sold]
```

---

## 3. Access matrix (who sees which section)

✅ = full · 👁 = limited/own-only · — = no access

| Section | Broker | Vendor | Agent | V.Solicitor | B.Solicitor | Buyer | Photographer |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| Dashboard | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Properties (create/manage) | ✅ | — | — | — | — | — | — |
| Participants | ✅ contacts | 👁 names | 👁 names | 👁 names | 👁 names | 👁 names | 👁 names |
| Valuations | ✅ all | ✅ report | 👁 own | — | — | — | — |
| Viewings | ✅ all | ✅ all | 👁 own | — | — | — | — |
| Feedback | ✅ all | ✅ all | 👁 own | — | — | — | — |
| Offers | ✅ all+detail | ✅ (no contacts) | 👁 own | — | — | — | — |
| Documents | ✅ all | 👁 by type | 👁 by type | 👁 by type | 👁 by type | 👁 by type | 👁 photos |
| AML / KYC | ✅ all | — | 👁 vendor only | ✅ | ✅ | — | — |
| Photography | ✅ | ✅ | — | — | — | — | ✅ |
| Introductions | ✅ curate | ✅ after offer | — | — | — | ✅ after offer | — |
| Notifications | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Admin (users/invites) | ✅ | — | — | — | — | — | — |

### Document visibility by type

| Role | Document types they can see |
|------|------------------------------|
| broker | **everything** |
| vendor | photo, floorplan, EPC, brochure, memo of sale, agent terms |
| agent | photo, floorplan, EPC, agent brochure, memo of sale, agent terms, **vendor AML**, AML verification, **+ their own uploads** |
| vendor_solicitor | vendor AML, AML verification, title register, planning, memo of sale, EPC, proof of funds |
| buyer_solicitor | buyer AML, AML verification, title register, planning, memo of sale, EPC, proof of funds, survey |
| buyer | memo of sale, EPC, brochure |
| family_office | brochure, EPC |
| photographer | photo, floorplan, EPC |

> Everyone can always see **documents they uploaded themselves** (so an agent sees
> their own buyer proof-of-funds even though other agents can't).

---

## 4. Alerts / notifications — who is told, and when

| Event | Broker | Vendor | Agent (the one) | Solicitors |
|-------|:--:|:--:|:--:|:--:|
| Viewing booked (instant) | 🔔 | — | — | — |
| Viewing requested (confirm mode) | 🔔 | 🔔 | — | — |
| Viewing confirmed / declined | — | — | 🔔 | — |
| Feedback submitted | 🔔 | — | — | — |
| Valuation submitted | 🔔 | — | — | — |
| Offer submitted | 🔔 | 🔔 | — | — |
| Offer accepted / declined / countered | — | — | 🔔 | — |
| **Offer accepted** → post-acceptance workflow | 🔔 (action items) | 🔔 | — | 🔔 vendor solicitor |

> AML capture, document uploads/shares, photography booking and introductions are
> recorded in the **audit log** but don't currently raise a notification. (Easy to
> add alerts to any of these if you want them.)

---

## 5. Per-persona journeys

### 👤 Vendor (seller)
```mermaid
flowchart LR
  V1[Accept invite] --> V2[Complete AML/KYC]
  V2 --> V3[Read valuation report]
  V3 --> V4[Confirm photo shoot date]
  V4 --> V5[Read viewing feedback - text + voice]
  V5 --> V6[Review offers, accept/decline]
  V6 --> V7[Solicitor introduced]
  V7 --> V8[Use 3rd-party introductions]
```
- **Can:** see valuations report, all viewings & feedback, all offers, the participant list, photography, post-offer introductions.
- **Cannot:** see agents'/solicitors' contact details, broker's private notes, negotiator contact on offers, buyer AML/proof-of-funds files.
- **Alerts:** new offer received; viewing requested (confirm mode); offer accepted.

### 🏢 Estate agent
```mermaid
flowchart LR
  A1[Accept invite] --> A2[Submit valuation]
  A2 --> A3[Access vendor AML + photos/floorplans]
  A3 --> A4[Book viewings]
  A4 --> A5[Submit feedback - type or voice]
  A5 --> A6[Submit offer + upload buyer PoF/AML]
  A6 --> A7[Get accept/decline/counter alert]
```
- **Can:** submit a valuation (sees only their own), book viewings, log feedback, submit offers, upload buyer documents, see vendor AML + photos/floorplans for brochures, see participants **by name**.
- **Cannot:** see other agents' valuations, viewings, feedback or offers; see anyone's contact details; see other agents' buyer documents.
- **Alerts:** their viewing confirmed/declined; their offer accepted/declined/countered.

### ⚖️ Solicitors (vendor & buyer)
```mermaid
flowchart LR
  S1[Invited after offer accepted] --> S2[Receive memo of sale]
  S2 --> S3[Upload AML/KYC for their party]
  S3 --> S4[Access conveyancing documents]
```
- **Can:** upload & certify AML/KYC, see conveyancing documents (title, planning, memo, proof of funds, etc.), see participants by name.
- **Cannot:** see valuations, viewings, feedback, offers, or the other side's private files.
- **Alerts:** vendor solicitor is notified when an offer is accepted.

### 📷 Photographer
```mermaid
flowchart LR
  P1[Accept invite] --> P2[Coordinate shoot date with vendor]
  P2 --> P3[Upload photos + floorplans directly]
```
- **Can:** view/coordinate the photography booking, upload photos & floorplans, see participants by name.
- **Cannot:** see valuations, offers, feedback, AML, or any sensitive documents (only photo/floorplan/EPC).
- **Alerts:** none currently.

### 🔑 Buyer
```mermaid
flowchart LR
  B1[Invited after offer accepted] --> B2[See memo of sale + EPC]
  B2 --> B3[Request 3rd-party introductions]
```
- **Can:** see memo of sale, EPC, brochure; request introductions (designers, builders, removals, cleaners, gardeners); see participants by name.
- **Cannot:** see other offers, feedback, valuations, or contact details.
- **Alerts:** none currently (candidate for "offer accepted — welcome" alert).

### 🤝 Third parties (designers, builders, removals, etc.)
- Not platform logins. They appear in **Introductions** (curated by the broker) and,
  once engaged, in the **Participants → third-party services** list.
- **Broker** sees their contact details + referral fees; everyone else sees company + service only.

### 🏛 INHOUS broker (the hub)
- Sees and manages **everything**: all properties, full contact directory, every
  document, all valuations/viewings/feedback/offers, AML, photography, introductions
  (incl. fees), and Admin (create users / send invites).
- Receives the most alerts (offers, feedback, valuations, viewing activity, and the
  post-acceptance action checklist).

---

## 6. Confidentiality summary (what each role is BLOCKED from)

```mermaid
flowchart TD
  subgraph Hidden from external parties
    H1[Other parties' email and phone]
    H2[Broker private notes]
    H3[Negotiator contact on offers - vendor view]
  end
  subgraph Hidden from agents
    A1[Other agents' valuations / viewings / feedback / offers]
    A2[Other agents' buyer AML and proof of funds]
  end
  subgraph Hidden from buyer/photographer/family office
    B1[Valuations, feedback, offers, full document vault]
  end
```

---

*Status: reflects the platform as built. The only planned feature not yet live is
the **brochure builder** (assemble photos + floorplans into a brochure) — coming next.*
