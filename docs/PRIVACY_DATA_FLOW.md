# PolicyNest Privacy Architecture & Data Flow Specification

**Compliance Standards:** Digital Personal Data Protection (DPDP) Act 2023, IRDAI POSP Guidelines 2015, Aadhaar Act 2016 (Masking Regulations).

---

## 1. Data Classification Matrix

| Data Category | Specific Elements | Statutory Basis | Masking / Storage Policy |
|---|---|---|---|
| **Public Information** | POSP Certificate Number, POSP Full Name, Licensing Date, Issuing Broker | IRDAI POSP Registry Verification | Stored plaintext; exposed via zero-auth verification endpoint |
| **Operational State** | Stage, Status, Review Notes, Audit Events, Training Hours, Exam Scores | IRDAI Licensing Compliance | Stored in database; internal review notes masked from applicants |
| **Confidential PII** | Full Legal Name, Date of Birth, Residential Address, Mobile Number, Email | KYC Identification & Appointment | Mobile masked as `••••••1234` in UI; Name verified against PAN |
| **Highly Sensitive PII** | Aadhaar Number, Bank Account Number, PAN Card Image, Identity marksheets | Statutory KYC Verification | **Aadhaar:** Stored ONLY as `XXXXXXXX1234`<br>**Bank:** Stored ONLY as `••••••••5678`<br>**Images:** Stored content-addressed with EXIF metadata stripped |

---

## 2. On-Device Document Processing & Data Minimization

PolicyNest pioneers an **on-device document analysis architecture**:
1. When an applicant selects a file in their browser, the client-side WebAssembly OCR engine (Tesseract.js / pdf.js) reads the image locally.
2. The browser validates document format, aspect ratio, blur, glare, and resolution before any bytes are transmitted across the network.
3. If a document fails quality gates (e.g. blurry image or incorrect document type), the file is refused **instantly in the browser**, preventing unnecessary transmission and storage of defective identity files.
4. Raw unmasked 12-digit Aadhaar numbers and biometric data are never extracted into persistent database storage.

---

## 3. Data Retention & Deletion Schedule

1. **Abandoned Incomplete Drafts:**
   Draft applications with no activity for 30 days are purged automatically from device storage and staging caches.
2. **Action Required Rework Window:**
   When changes are requested, applicants have a statutory 14-day window to provide revised documents before the case times out.
3. **Certified POSP Records:**
   In accordance with IRDAI regulations, appointment agreements, exam attempts, training completion logs, and certificate records are retained for a minimum statutory period of 10 years following appointment.
4. **Data Principal Rights (DPDP Act 2023):**
   Applicants may request download of their complete data pack or deletion of unsubmitted draft records via the Profile & Settings cockpit.
