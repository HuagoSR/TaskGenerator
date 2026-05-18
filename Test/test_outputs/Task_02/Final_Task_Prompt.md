**To:** Junior AI Auditor
**From:** Senior Audit Partner
**Date:** October 26, 2023
**Subject:** Assignment: Q3 Tour Operations P&L Reconciliation and Compliance Audit

We have been engaged to perform a targeted financial review of the tour operations data. Your objective is to process the raw transaction logs into a structured Profit & Loss (P&L) report while ensuring tax compliance and currency accuracy for our European jurisdictions.

Please execute the following audit program precisely:

### 1. Data Ingestion and Pre-Processing
*   **Source Files:** Utilize `Tour_Data.xlsx`, `Tax_Rates.csv`, and `Currency_Rates.xlsx`.
*   **Data Integrity:** Identify all records where the `PreTax` field contains null values. You are required to process these—either through imputation or exclusion based on standard materiality—to ensure the final P&L is not skewed.
*   **Scope Filtering:** Limit the audit scope strictly to records where the host country is either **'France'** or **'Germany'**.

### 2. Tax and Compliance Calculations
*   **Tax Application:** Perform a lookup against `Tax_Rates.csv` using the `Country` column. 
*   **Net Revenue Calculation:** Calculate the `Net_Revenue_After_Tax` for each transaction.
*   **Compliance Adjustment:** To account for the new regulatory surcharge, generate a new column named `CompliantAmount` by multiplying the `PreTax` value by a factor of **1.05**.

### 3. Currency Translation
*   **Exchange Rates:** Refer to `Currency_Rates.xlsx` to obtain the relevant conversion factors.
*   **Local Reporting:** Convert the `Net_Revenue_After_Tax` into the local currency and store this in a column titled `Local_Currency_Amount`.

### 4. Financial Reporting (P&L)
*   Construct a comprehensive P&L report that summarizes:
    *   **Total Net Revenue**
    *   **Total Expenses**
    *   **Net Income**
*   **Hard Constraint:** The final Excel workbook must include a dedicated sheet named **`Derived_USD_Rates`** showing the underlying exchange rate logic used for the translation.

### 5. Deliverables
*   **Audit Summary:** Draft a formal 'Task Completion Summary'. This must be exported as a separate PDF document.
*   **Naming Convention:** The summary document **MUST** be named exactly **`task_summary.pdf`**.

Accuracy is non-negotiable. Ensure that the join between the tour data and tax rates is seamless to avoid leakage in the revenue reporting. I expect the working papers and the final PDF on my desk by the end of the cycle.

**Sign-off,**

*Senior Audit Partner*

### Critical Auto-Appended Constraints:
- The final summary MUST be named 'task_summary.pdf'.
- Include a sheet named 'Derived_USD_Rates'.
