**Context**
You are an auditor tasked with a substantive financial review of international touring operations for a major entertainment client. Your objective is to reconcile disparate financial ledgers provided by the Tour Manager and the Production Company, apply jurisdictional tax treatments, and standardize the financial presentation into a consolidated Profit & Loss statement. 

**Audit Objectives**
**1. Data Consolidation & Integrity**
Integrate the raw income, costs, and tax withholding streams from all originating sources. The completeness of the Gross Revenue ledger is a critical audit dependency; any missing or null entries within this field must be resolved according to standard data quality assumptions prior to executing any financial calculations. To preserve the unmodified state of the initial client records, the consolidated, pre-processed data must be archived immediately.

**2. Jurisdictional Tax & Revenue Standardization**
Assess international tax liabilities by applying specific statutory withholding rates based on the tour stop's jurisdiction (UK: 20%, France: 15%, Spain: 24%, Germany: 15.825%). The resulting Net Revenue must be derived by deducting these localized tax burdens from the Gross Revenue. Following this deduction, all revenue figures must be standardized into USD to ensure a unified currency basis for the final reporting.

**3. Expense Categorization & P&L Consolidation**
Classify all operational expenditures into standardized audit buckets: Band and Crew, Other Tour Costs, Hotel & Restaurants, and Other Travel Costs. Once expenditures are categorized and revenues are standardized, aggregate the financial data by its originating Source. The final consolidated view must calculate Total Net Revenue, Total Expenses, and the resulting Net Income across these sources.

**Working Paper Format (The Schema)**
To maintain a clear audit trail and facilitate review, your analytical dataset must conceptually append or map the following fields prior to final aggregation:
*   **Standardized Expense Category:** The mapped classification of raw operational expenses into the four approved audit buckets.
*   **Jurisdictional Tax Rate:** The applicable statutory withholding percentage based on the tour stop's country.
*   **Calculated Withholding Amount:** The monetary tax deduction derived from the Gross Revenue.
*   **Net Revenue (USD):** The post-tax revenue, fully converted and standardized to USD.
*   **Source-Level Aggregates:** The calculated Total Net Revenue, Total Expenses, and Net Income, grouped by the originating entity (Tour Manager vs. Production Company).

**Hard Constraints & Deliverables**
1.  **Raw Data Archive:** The initial consolidation of unmodified client datasets must be exported and saved exactly as `raw_financials.xlsx`.
2.  **Final P&L Report:** The fully aggregated financial model must be generated as a formatted Excel report. It must feature the header 'As of 12/31/2024', utilize professional column labels, ensure proper USD currency alignment, and be saved exactly as `profit_and_loss_report.xlsx`.
3.  **Audit Summary:** A formal task completion summary detailing the reconciliation process must be drafted and saved exactly as `task_summary.pdf`.

### Critical Auto-Appended Constraints:
- The final summary MUST be named 'task_summary.pdf'.
