# PolicyNest 3D & Spatial Web Experience Architecture

**Framework:** Pure CSS 3D Transforms + Procedural SVG/Canvas  
**Bundle Footprint:** < 45 KB overhead, 0 external WebGL/GLTF dependencies  
**Rendering Performance:** Consistent 60 FPS on mid-range Android mobile devices  

---

## 1. Architectural Strategy: CSS 3D & Canvas Over Heavy WebGL

PolicyNest purposefully uses **CSS 3D perspective transforms with procedural SVGs** rather than heavy Three.js / WebGL bundles for the following key reasons:
1. **Financial Trust & Reliability:** Commercial insurance agents across Tier-2/Tier-3 Indian cities frequently use affordable Android devices or older mobile browsers where WebGL contexts frequently crash or get lost on background tabs.
2. **Instant Interactive Readiness:** Zero loading delay. No 2 MB 3D engine download before the applicant can see their onboarding checklist.
3. **Accessibility First:** CSS 3D elements remain real, live DOM nodes (`<button>`, `<section>`, `<article>`), meaning screen readers, assistive technology, and keyboard navigation work out-of-the-box with zero custom accessibility shims.
4. **Memory Hygiene:** Zero GPU memory leaks upon route navigation.

---

## 2. Core Purposeful 3D Experience Modules

### 1. The Interactive Onboarding Journey Map (Idea 1)
- **Viewport:** Displayed in the Public Landing Hero and Applicant Dashboard.
- **Visual:** Isometric pathway featuring 8 stations:
  1. *Profile* (`PN-ST-01`)
  2. *Identity* (`PN-ST-02`)
  3. *Documents* (`PN-ST-03`)
  4. *Verification* (`PN-ST-04`)
  5. *Training* (`PN-ST-05`)
  6. *Examination* (`PN-ST-06`)
  7. *Review* (`PN-ST-07`)
  8. *Certification* (`PN-ST-08`)
- **Interactive Behavior:** Stations elevate on hover/focus (`translateZ(24px)`). Clicking any station opens an accessible explanation modal showing prerequisites, current status, and estimated duration.
- **Fallback:** Automatic 2D vertical timeline on mobile viewports (< 768px) and in Simplified View mode.

### 2. Interactive Document Vault (Idea 2)
- **Viewport:** Displayed on Applicant Documents Step (`#documents`).
- **Visual:** Secure isometric file cabinet with 5 distinct slot trays (`PAN`, `AADHAAR_FRONT`, `AADHAAR_BACK`, `CLASS10`, `BANK`).
- **Slot States:**
  - *Empty:* Muted outline tray with upload prompt.
  - *Processing:* Scanning laser sweep animation.
  - *Verified:* Raised tray with emerald wax seal checkmark.
  - *Rework Required:* Highlighted amber tray with defect guidance badge.
- **Fallback:** Structured accessible document table.

### 3. Verification Constellation (Idea 3)
- **Viewport:** Displayed on Verification Step and Reviewer Case Dossier.
- **Visual:** Interactive node graph linking:
  `[Applicant Identity]` $\leftrightarrow$ `[PAN Database]` $\leftrightarrow$ `[Aadhaar Verhoeff]` $\leftrightarrow$ `[Bank Penny Drop]` $\leftrightarrow$ `[IRDAI Central Registry]` $\leftrightarrow$ `[Underwriter Desk]`.
- **Interactivity:** Clicking any node reveals the exact deterministic rule applied (§2.1, §4.2), whether the adapter is simulated or live, and what data fields were compared.

### 4. Training Knowledge Campus (Idea 4)
- **Viewport:** Displayed on Training Step (`#training`).
- **Visual:** Structured 3D bookshelf / learning academy displaying the 5 modules with real-time hours studied progress bar and sequential lock status.

### 5. Exam Readiness Ring (Idea 5)
- **Viewport:** Displayed prior to launching the examination.
- **Visual:** Multi-segment status ring displaying training clearance (15h), KYC status, and attempt allowances.

### 6. Certificate Reveal (Idea 8)
- **Viewport:** Displayed upon completing agreement execution.
- **Visual:** Restrained 3D unfolding of the official POSP certificate card, accompanied by cryptographic HMAC-SHA256 seal stamp.

### 7. Privacy Data-Flow Explainer (Idea 9)
- **Viewport:** Displayed on Landing Page and Privacy Settings.
- **Visual:** 3-tier spatial model showing:
  - Tier 1: Client Browser (On-Device OCR, zero image transmission)
  - Tier 2: PolicyNest Server (Masked identifiers, WAL persistence)
  - Tier 3: Statutory Registries (Sandbox adapters, encrypted tokens)
