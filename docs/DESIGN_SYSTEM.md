# PolicyNest Design System & Spatial Token Architecture

**Version:** 2026.4.1  
**Target:** Financial-Services Trust, Indian Regulatory Clarity, Human Warmth  

---

## 1. Design Tokens

### 1.1 Color Tokens

```css
:root {
  /* Canvas & Surfaces */
  --bg: #fffdfa;
  --surface: #ffffff;
  --surface-raised: #ffffff;
  --sunken: #faf5ec;
  --line: #efe6d8;
  --line-strong: #dfd2be;
  --dot: #e6d9c4;

  /* Typography & Ink */
  --ink: #2b2118;
  --ink-soft: #4a3c2e;
  --muted: #7b6b5a;
  --ink-on-brand: #ffffff;

  /* Brand Palette (Indian Financial Trust - Saffron & Amber) */
  --brand: #c8501a;
  --brand-hover: #b04313;
  --brand-soft: #fdebdd;
  --brand-glow: rgba(200, 80, 26, 0.25);
  --accent: #e39a2b;
  --accent-soft: #fdf2da;

  /* Authoritative Status Colors (With Dual-Layer Soft Backgrounds) */
  --ok: #1c7c4c;
  --ok-soft: #e4f4e9;
  --ok-glow: rgba(28, 124, 76, 0.25);

  --warn: #a2610a;
  --warn-soft: #fdf1d8;
  --warn-glow: rgba(162, 97, 10, 0.25);

  --bad: #b3372b;
  --bad-soft: #fbe6e3;
  --bad-glow: rgba(179, 55, 43, 0.25);

  --lav: #5b3e9b;
  --lav-soft: #f2eefa;

  /* Elevation & Spatial Shadows */
  --shadow-sm: 0 1px 2px rgba(74, 48, 20, 0.05);
  --shadow-md: 0 4px 6px -1px rgba(74, 48, 20, 0.06), 0 2px 4px -1px rgba(74, 48, 20, 0.04);
  --shadow-lg: 0 10px 15px -3px rgba(74, 48, 20, 0.08), 0 4px 6px -2px rgba(74, 48, 20, 0.04);
  --shadow-spatial: 0 20px 35px -10px rgba(74, 48, 20, 0.15), 0 0 1px 1px rgba(74, 48, 20, 0.05);

  /* Spatial Lighting */
  --perspective: 1200px;
  --isometric-angle: rotateX(25deg) rotateY(-15deg);
  --radius-card: 14px;
  --radius-pill: 9999px;
}

html[data-theme="dark"] {
  --bg: #14110e;
  --surface: #1e1a16;
  --surface-raised: #28231e;
  --sunken: #181410;
  --line: #332b23;
  --line-strong: #453a2f;
  --dot: #2a231b;

  --ink: #f7f3ed;
  --ink-soft: #dcd3c7;
  --muted: #a69888;
  --ink-on-brand: #ffffff;

  --brand: #e06227;
  --brand-soft: #381c10;
  --brand-glow: rgba(224, 98, 39, 0.35);
  --accent: #f0aa38;
  --accent-soft: #382710;

  --ok: #28a764;
  --ok-soft: #123320;
  --warn: #c98018;
  --warn-soft: #36220b;
  --bad: #d94536;
  --bad-soft: #3b1411;

  --shadow-spatial: 0 25px 45px -15px rgba(0, 0, 0, 0.6), 0 0 1px 1px rgba(255, 255, 255, 0.08);
}
```

---

## 2. Spatial Isometric Architecture

### Perspective Container Rules:
1. Every 3D visual container defines `perspective: 1000px` to `1200px`.
2. Interactive stations utilize `transform-style: preserve-3d`.
3. Elevation levels:
   - Ground level: `translateZ(0px)`
   - Floating node: `translateZ(16px)`
   - Hovered milestone: `translateZ(28px)` with soft spread shadow
   - Active focus ring: `outline: 3px solid var(--brand)` at `translateZ(32px)`.

---

## 3. Status Communication Principles

Status must **never** be communicated by color alone. Every status element incorporates three redundant channels:
1. **Color Tint:** Standard semantic hue.
2. **Iconography:** Checkmark (pass/verified), clock/pulse (processing), alert-triangle (action required), shield (secured).
3. **Explicit Text Label:** Bilingual string (`Verified`, `Changes Requested`, `In Progress`, `Pending Exam`).
