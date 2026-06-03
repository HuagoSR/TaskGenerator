**Context**
You are an auditor tasked with a substantive review of the Anti-Financial Crime (AFC) Risk Metrics for the Q2 and Q3 2024 periods. The baseline population data is provided in `population_metrics.xlsx`. Your objective is to perform a targeted risk assessment, calculate an appropriate statistical sample size, and extract a highly concentrated sample for further substantive testing.

**Audit Objectives**
*   **Baseline Preservation:** As part of the initial documentation process, ensure the initial raw data is exported and preserved in `population_metrics.xlsx`.
*   **Sample Size Determination:** Establish the required testing sample size leveraging standard statistical parameters: a 90% confidence level and a 10% tolerable error rate.
*   **Target Risk Profile Evaluation:** Evaluate the population against key AFC risk indicators. The target risk profile encompasses:
    *   Significant quarter-on-quarter metric volatility (variance exceeding 20%).
    *   Dormant metric behavior (zero values across both the Q2 and Q3 periods).
    *   Exposure to high-risk jurisdictions (Cayman Islands, Pakistan, UAE).
    *   Vulnerable business lines (Trade Finance, Correspondent Banking).
    *   Specific entities of heightened interest ('CB Cash Italy', 'CB Correspondent Banking Greece', 'IB Debt Markets Luxembourg', 'CB Trade Finance Brazil', 'PB EMEA UAE').
    *   Critical control metric codes (A1, C1).
*   **Sample Extraction Strategy:** Extract a representative sample exactly matching the calculated sample size. The extraction strategy must ensure baseline coverage across all Divisions and sub-Divisions, while strictly isolating items that exhibit at least one characteristic of the Target Risk Profile defined above. 

**Data Quality Assumptions**
Prior to variance evaluation, any missing entries or negative values in the Q2 and Q3 metrics should be addressed per standard audit data cleansing protocols to ensure accurate quarter-on-quarter comparisons.

**Working Paper Format (The Schema)**
To maintain a clear audit trail, your final dataset must append indicator columns representing the conceptual risk evaluations. The required output schema for the sample data includes:
*   `QoQ_Variance`: The calculated proportional change between Q2 and Q3.
*   `Risk_Volatility_Flag`: Indicator for variance exceeding the 20% threshold.
*   `Risk_Dormant_Flag`: Indicator for zero-value persistence across both periods.
*   `Risk_Jurisdiction_Flag`: Indicator for alignment with the specified high-risk countries.
*   `Risk_BusinessLine_Flag`: Indicator for alignment with vulnerable business lines.
*   `Risk_Entity_Flag`: Indicator for alignment with the specific entities of interest.
*   `Risk_MetricCode_Flag`: Indicator for critical metric codes.
*   `Final_Selection_Indicator`: A binary marker (1) denoting the row's inclusion in the final substantive sample.

**Hard Constraints & Deliverables**
1.  **Sample Working Paper:** Export the finalized selection to a spreadsheet named `Sample.xlsx`. This workbook must contain two distinct sheets: Tab 1 containing the selected sample data (including all schema columns defined above), and Tab 2 documenting the sample size calculation workings.
2.  **Audit Summary:** Draft a Task Completion Summary detailing the methodology, parameters, and findings of your extraction. This document MUST be named `task_summary.pdf`.

### Critical Auto-Appended Constraints:
- The final summary MUST be named 'task_summary.pdf'.
