# PolicyNest Deterministic Sandbox Provider Adapters

## 1. Adapter Strategy & Philosophy

In compliance with Indian insurance regulatory guidelines (IRDAI POSP Guidelines 2015/2019) and zero-cost local architecture:
- Regulated third-party verification APIs (NSDL PAN, UIDAI Aadhaar, NPCI Penny-Drop, IRDAI Central Registry) require institutional enterprise agreements and paid credentials.
- In this environment, PolicyNest implements **Deterministic Sandbox Provider Adapters**.
- Each adapter has honest labels (`SANDBOX` / `SIMULATED`), simulates realistic network latency (50-150ms), and provides deterministic pass, fail, mismatch, and conflict test scenarios triggered by well-defined input patterns.

---

## 2. Adapter Catalog & Deterministic Triggers

### 2.1 PAN Verification Adapter (`PanVerificationProvider`)
- **Simulates**: NSDL / Income Tax Department PAN Verification API.
- **Triggers**:
  - `ABCDE1234F`: Standard PASS (Name match: Aarav Patel, Status: Active/Operative).
  - Contains `INVALID` or ends with `0000X`: Returns `PAN_NOT_FOUND` (404).
  - Contains `MISMATCH`: Returns `NAME_MISMATCH` (Extracted name diverges from submitted name).
  - Contains `TIMEOUT`: Simulates 504 Gateway Timeout for retry testing.

### 2.2 Aadhaar e-KYC Adapter (`AadhaarKycProvider`)
- **Simulates**: UIDAI Offline e-KYC (XML + 4-digit share code).
- **Triggers**:
  - Any 12-digit number (e.g. `9999 4123 4567`): Standard PASS with demographic data and masked Aadhaar `XXXXXXXX4567`.
  - Share code `0000`: Returns `INVALID_SHARE_CODE`.
  - Number ending with `8888`: Returns `AGE_INELIGIBLE` (Calculated age < 18 years, failing IRDAI POSP criteria).

### 2.3 Bank Penny-Drop Adapter (`BankPennyDropProvider`)
- **Simulates**: NPCI Immediate Payment Service (IMPS) ₹1.00 Penny-Drop Verification.
- **Triggers**:
  - Valid IFSC + Account: Standard PASS with beneficiary name returned from simulated CBS.
  - Account containing `999`: Returns `ACCOUNT_INVALID` / `BENEFICIARY_NAME_MISMATCH`.
  - Account containing `FROZEN`: Returns `ACCOUNT_BLOCKED`.

### 2.4 Facial Liveness & Biometric Match Adapter (`FaceMatchProvider`)
- **Simulates**: AI Face Detection, Eye-Blink Liveness, and 1:1 ID Photo Comparison.
- **Triggers**:
  - Normal Selfie: PASS (Similarity: 0.94, Liveness: 0.98).
  - Test input `MISMATCH`: Similarity 0.42 (below 0.80 threshold).
  - Test input `STATIC_IMAGE`: Liveness 0.31 (fails anti-spoofing liveness check).

### 2.5 IRDAI Central Registry Adapter (`IrdaiRegistryProvider`)
- **Simulates**: Central IRDAI Agent Appointment Database (Ensuring candidate is not currently appointed with another insurer).
- **Triggers**:
  - Standard PAN: PASS (Zero active appointments, eligible for appointment).
  - PAN ending with `9999F` or containing `CONFLICT`: Returns `DUPLICATE_APPOINTMENT` (Active appointment found with HDFC ERGO General Insurance Co. Ltd.; prohibited under POSP regulations).

### 2.6 Antivirus & Malware Scanner Adapter (`MalwareScannerProvider`)
- **Simulates**: Enterprise file inspection engine scanning incoming document streams.
- **Triggers**:
  - Normal PNG/JPEG/PDF: Clean file, SHA-256 hash computed, allowed.
  - File containing string `EICAR` or filename containing `virus`/`infected`: Immediate quarantine, returns `MALWARE_DETECTED`.

---

## 3. Production Transition Blueprint

To transition from Sandbox Adapters to live third-party providers in staging/production:
1. Implement the standardized interface defined in `providers.py`.
2. Configure credentials in environment variables (`NSDL_API_KEY`, `UIDAI_AUA_CODE`, `NPCI_MERCHANT_KEY`).
3. Set `POLICYNEST_ENV=PRODUCTION` in `.env`.
4. The system automatically switches adapter dispatch to the live HTTPS REST client while preserving identical internal data structures.
