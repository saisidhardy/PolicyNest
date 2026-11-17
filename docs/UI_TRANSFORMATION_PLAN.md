# PolicyNest UI & Visual Experience Transformation Plan

**Date:** 2026-11-17  
**Author:** Principal Product Designer, Interaction Designer & Frontend Architect  
**Target Deployments:** Embarko (`https://policynest.embarko.app/`), GitHub Pages (`https://saisidhardy.github.io/PolicyNest/`)  
**Standard:** WCAG 2.2 AA, IRDAI Guidelines, DPDP Act 2023  

---

## 1. Current State Audit

### 1.1 Architecture & Stack Summary
- **Frontend Framework:** Standalone zero-bloat vanilla JavaScript application (`policynest_mvp/PolicyNest.html`) wrapped by `build_site.py`.
- **Styling Architecture:** Modern CSS custom properties with responsive Grid/Flexbox layouts, warm neutral palette, and dark mode support (`html[data-theme="dark"]`).
- **Icons & Visuals:** Pure inline SVG glyphs without external asset dependencies.
- **Client Processing:** Client-side WASM OCR via Tesseract.js 5.1 and PDF.js 3.11.
- **Backend Architecture:** Modular Python services with SQLite 3 (WAL mode), 11-role ABAC policy engine, and deterministic underwriting rules.

### 1.2 Design Strengths to Preserve
- **Human-Centric Copy:** Clean, reassuring, jargon-free explanations in English and Hindi.
- **One-Task-At-A-Time Stepper:** Low cognitive load for first-time insurance POSP applicants.
- **Privacy Transparency:** Clear on-device OCR privacy notices and honest disclosures.
- **Zero Third-Party Tracking Bloat:** Lightweight footprint with fast load time (< 500ms).

### 1.3 Design Weaknesses & Opportunities for Spatial Depth
- **Flat Process Visibility:** The current 6-step timeline lacks spatial hierarchy and tactile milestone feedback.
- **Abstract Document Storage:** Document upload slots are currently displayed as flat form fields rather than an organized, secure "Document Vault".
- **Opaque Verification Relationships:** Applicants cannot intuitively see how their PAN, Aadhaar, and Bank proof connect to form an approved identity.
- **Understated Milestones:** Passing the exam and achieving IRDAI POSP certification lacks a dignified, celebratory issuance moment.
- **Reviewer Cognitive Overhead:** Reviewers must read long lists of checks rather than inspecting a visual relationship graph of identity cross-checks.

---

## 2. Where 3D / Isometric Experiences Add Value vs Reduce Usability

### High-Value Purposeful 3D / Isometric Applications:
1. **The Onboarding Journey Map:** An isometric landscape representing the 8 stations (Profile, Identity, Documents, Verification, Training, Examination, Review, Certification). Provides spatial orientation without cluttering forms.
2. **Interactive Document Vault:** An organized isometric document cabinet showing 5 slots (PAN, Aadhaar Front, Aadhaar Back, Class 10, Bank Statement) with visual status indicators (Empty, Scanning pulse, Verified seal, Rework needed).
3. **Verification Constellation:** An interactive node-relationship diagram showing data linkages (Name match tier, Age eligibility, Bank penny drop) with plain-language explainer drawers.
4. **Training Knowledge Campus:** Isometric academy bookshelf visualizing 15 hours across 5 regulatory modules.
5. **Exam Readiness Ring:** Multi-factor ring dashboard displaying training hours, KYC clearance, and attempt availability.
6. **Certificate Reveal:** Restrained 3D seal stamping and card reveal upon passing the exam and executing the agreement.
7. **Privacy Data-Flow Explainer:** Spatial 3-column architecture explaining what stays on-device vs server vs statutory registries.

### Where 3D Reduces Usability (STRICTLY FORBIDDEN):
- **Data-Entry Form Controls:** Text inputs, dropdowns, date pickers, and checkboxes must remain conventional, highly accessible 2D form elements.
- **Examination Question Interface:** Exam questions, options, and countdown timers must use standard readable typography with high-contrast radio controls.
- **Underwriting Decision Actions:** Reviewer approval/rejection buttons must remain clear, high-contrast, unambiguous 2D controls.
- **Background Animations:** Constantly moving or distracting 3D backgrounds behind reading text are strictly barred.

---

## 3. Visual Language & Design Tokens

### 3.1 Color & Spatial Palette
- **Brand Primary:** `#c8501a` (Deep Saffron / Terracotta - warm, authoritative, financial-services trust).
- **Brand Accent:** `#e39a2b` (Warm Amber - progress, energy, guidance).
- **Surfaces:** `#ffffff` (Card surface), `#fffdfa` (Warm canvas background), `#faf5ec` (Sunken background).
- **Status Green (Verified / Pass):** `#1c7c4c` (Deep Forest Emerald).
- **Status Amber (Needs Attention / Rework):** `#a2610a` (Warm Ochre).
- **Status Red (Defect / Rejected):** `#b3372b` (Crimson / Brick).
- **Status Purple (Review / Escalation):** `#5b3e9b` (Royal Iris).
- **Spatial Shadows:** Multi-layer soft elevation: `0 4px 6px -1px rgba(74,48,20,0.06), 0 20px 25px -5px rgba(74,48,20,0.1)`.

### 3.2 Typography
- **Display Headings:** `"Sora", "Segoe UI", system-ui, sans-serif` (refined geometric clarity).
- **Body Text:** `"Manrope", "Segoe UI", system-ui, sans-serif` (approachable legibility at all sizes).
- **Monospace Identifiers:** `"IBM Plex Mono", ui-monospace, Consolas, monospace` (tabular reference numbers).

---

## 4. Technical 3D & Motion Architecture

- **Technology Selection:** Pure CSS 3D Transforms (`perspective`, `transform-style: preserve-3d`, `rotateX`, `rotateY`, `translateZ`) coupled with SVG rendering and lightweight Canvas 2D effects.
- **Zero Asset Bloat:** 0 KB external WebGL/GLTF downloads. Instant load, zero memory leaks, full 60 FPS performance on low-end mobile devices.
- **Reduced Motion Support:** All transforms and keyframe animations automatically disable under `@media (prefers-reduced-motion: reduce)`.
- **Simplified View Toggle:** Built-in explicit user control ("Simplified 2D View" vs "Interactive Spatial View") accessible from the navigation bar.

---

## 5. Persona Experience Architecture

| Persona | Key Experience Requirements | Primary Spatial Visuals |
|---|---|---|
| **Public Visitor** | Orientation, trust, clear call-to-action, time estimation | Hero Journey Map, 8-Stage Stepper, Privacy Explainer |
| **Applicant** | Low cognitive load, immediate next action, progress clarity | Interactive Journey Map, Document Vault, Training Campus, Exam Ring, Certificate Reveal |
| **Reviewer** | High information density, SLA tracking, rapid decisioning | Multi-Queue Cockpit, Cross-Check Visualizer, Defect Action Panel |
| **Administrator** | Workload distribution, staff provisioning, compliance exports | Operational Metrics, Staff Management, Audit Pack Exporter |
| **Auditor / Compliance** | Immutable audit inspection, regulatory reports | Tamper-Evident Timeline, Cryptographic Audit Pack Inspector |

---

## 6. Implementation Phasing

1. **Phase 1-2:** Tokens, design system, and motion guidelines.
2. **Phase 3-8:** Purposeful spatial components (Journey Map, Vault, Constellation, Campus, Ring, Reveal, Privacy Explainer) and responsive views.
3. **Phase 9-12:** Accessibility enhancements (WCAG 2.2 AA, focus states, screen reader text alternatives, bilingual English/Hindi).
4. **Phase 13-21:** Persona audit, database verification, technical observability, and privacy-safe product analytics.
5. **Phase 22-28:** Automated test suites, manual verification, and production readiness reporting.
