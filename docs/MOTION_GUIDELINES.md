# PolicyNest Motion Design & Micro-Interaction Guidelines

**Standard:** Purposeful, restrained, accessible motion for high-trust financial onboarding.

---

## 1. Principles of Motion

1. **Orientation Before Animation:** Motion must orient the user in their multi-stage journey (e.g. moving smoothly from Documents to Verification) rather than distracting them.
2. **Deterministic Response:** Motion confirms user intent (saving draft, submitting document, passing milestone).
3. **Restraint:** No decorative bouncing, no looping spinners when progress is known, no continuous floating text.
4. **Reduced-Motion Mandate:** When `prefers-reduced-motion: reduce` is active, all spatial rotations, zooms, and translations collapse to clean instantaneous opacity fades or static states.

---

## 2. Micro-Interaction Token Catalog

| Micro-Interaction | Trigger | Duration | Easing | Spatial Effect |
|---|---|---|---|---|
| **Station Hover** | Mouse enter node | 240ms | `cubic-bezier(0.2, 0.8, 0.2, 1)` | `translateZ(16px)` + elevation shadow |
| **Stage Complete** | Server state update | 500ms | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Green checkmark seal settle |
| **Autosave Pulse** | Draft autosave | 300ms | `ease-in-out` | "Saving..." $\rightarrow$ "Saved just now" check |
| **Doc Scanning** | File upload | 1200ms | `linear` | Gentle horizontal scan pulse inside slot |
| **Certificate Reveal** | Issue certificate | 800ms | `cubic-bezier(0.16, 1, 0.3, 1)` | 3D card unfold + wax seal stamp |
| **Defect Alert** | Reviewer rejection | 400ms | `cubic-bezier(0.25, 1, 0.5, 1)` | Soft amber highlight border |

---

## 3. Reduced Motion & Simplified View Implementations

```css
@media (prefers-reduced-motion: reduce) {
  *, ::before, ::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  .journey-map-3d, .vault-cabinet-3d, .constellation-3d {
    transform: none !important;
    perspective: none !important;
  }
}

/* User-controlled Simplified View Toggle */
body.simplified-view .journey-map-3d,
body.simplified-view .vault-cabinet-3d,
body.simplified-view .constellation-3d {
  transform: none !important;
  perspective: none !important;
  display: block;
}
```
