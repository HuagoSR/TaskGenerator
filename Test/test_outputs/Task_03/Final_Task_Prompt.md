This task involves processing music festival transaction data to ensure tax compliance and financial accuracy for specific European regions. You will be required to perform data cleaning, filtering, tax calculations, and currency conversions.

### **Task Title: Music Festival Financial Compliance & Tax Processing**

#### **1. Data Ingestion & Initial Setup**
*   **Primary Dataset:** Load `festival_transactions.csv`.
*   **Reference Data 1:** Load `Tax_Rates.csv` (used for regional tax mapping).
*   **Reference Data 2:** Load `Currency_Rates.xlsx` (used for local currency conversion).

#### **2. Data Cleaning & Filtering**
*   **Null Handling:** Identify all records where the `PreTax` field is null. You must decide on a processing strategy (e.g., imputation with 0 or removal) to ensure calculations can proceed.
*   **Geographic Filtering:** Filter the dataset to include only records where the `host_country` is either **'France'** or **'Germany'**.

#### **3. Compliance & Tax Calculations**
*   **Compliance Adjustment:** Create a new column named `CompliantAmount` by multiplying the `PreTax` value by a factor of **1.05**.
*   **Tax Mapping:** Perform a join/match between the `region_name` column in the transaction dataset and the `Tax_Rates.csv` file.
*   **Net Revenue:** Calculate the `Net_Revenue_After_Tax` based on the matched tax rates and the `CompliantAmount`.

#### **4. Currency Conversion**
*   **Rate Application:** Use the exchange rates provided in `Currency_Rates.xlsx`.
*   **Local Calculation:** Convert the `Net_Revenue_After_Tax` into the local currency of the host country. Store this value in a new column named `Local_Currency_Amount`.

#### **5. Hard Constraints & Output Requirements**
*   **Final Dataset:** Export the processed data to a CSV file named **`Festival_Compliance_Result.csv`**.
*   **Internal Documentation:** During the conversion process, you must generate a data structure or secondary file that includes a sheet named **`Derived_USD_Rates`** to document the exchange logic used.
*   **Reporting:** Draft a 'Task Completion Summary' detailing the number of records processed and any null values handled. This document MUST be exported as a PDF named **`task_summary.pdf`**.

---

### **Summary of Expected Files:**
1.  **`Festival_Compliance_Result.csv`**: The final processed transaction list.
2.  **`task_summary.pdf`**: The formal summary of the processing steps and data integrity.
3.  **`Currency_Calculations.xlsx`** (or similar): Containing the mandatory **`Derived_USD_Rates`** sheet.

### Critical Auto-Appended Constraints:
- The final summary MUST be named 'task_summary.pdf'.
- Include a sheet named 'Derived_USD_Rates'.
