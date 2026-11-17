# PolicyNest Operational & Product Metric Definitions

This document defines the mathematical formulas, data sources, and operational targets for all platform dashboard metrics.

---

## 1. Funnel Conversion Metrics

### 1.1 Funnel Completion Rate (FCR)
- **Definition:** The proportion of applicants who start an application and reach full IRDAI certification.
- **Formula:** $\text{FCR} = \frac{\text{Count}(\text{Applications in CERTIFIED})}{\text{Count}(\text{Applications Started})} \times 100\%$
- **Target:** $> 65\%$ (industry benchmark for POSP agent platforms is ~35%).

### 1.2 First-Time Document Verification Rate (FTVR)
- **Definition:** Percentage of document uploads that clear local OCR quality gates and automated cross-checks without requesting rework.
- **Formula:** $\text{FTVR} = \frac{\text{Count}(\text{Documents with version}=1 \text{ and status}=\text{'VERIFIED'})}{\text{Count}(\text{Total unique slot uploads})} \times 100\%$
- **Target:** $> 85\%$ (enabled by on-device pre-flight quality checks).

### 1.3 Rework Recovery Rate (RRR)
- **Definition:** The percentage of candidates asked to fix a defective document who successfully resubmit and clear KYC.
- **Formula:** $\text{RRR} = \frac{\text{Count}(\text{Resubmissions Approved})}{\text{Count}(\text{Applications in NEEDS\_MORE\_INFO})} \times 100\%$
- **Target:** $> 75\%$.

---

## 2. Operational Underwriting Metrics

### 2.1 Median Reviewer Turnaround Time (TAT)
- **Definition:** The median elapsed time in hours between an application submission (`submitted_at`) and the initial underwriting decision (`decided_at`).
- **Formula:** $\text{Median}(\text{decided\_at} - \text{submitted\_at}) / 3600$
- **Target:** $< 4.0\text{ hours}$ (SLA limit: 24.0 hours).

### 2.2 Exam First-Attempt Pass Rate
- **Definition:** Percentage of exam attempts passed on the initial attempt (score $\ge 35\%$).
- **Formula:** $\frac{\text{Count}(\text{attempt\_number}=1 \text{ and passed}=1)}{\text{Count}(\text{attempt\_number}=1)} \times 100\%$
- **Target:** $> 80\%$ (supported by the 15-hour structured curriculum).
