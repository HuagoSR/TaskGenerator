Welcome to the team. I have an upcoming audit engagement that requires your immediate attention. 

We need to prepare a structured Excel profit and loss (P&L) report using the provided 'Tour_Data.xlsx' file. Please note that all initial financial figures provided in this dataset are in USD. Your primary objective is to calculate the Total Net Revenue, Total Expenses, and Net Income for the tour.

To ensure accurate international tax reporting, you must match the 'Country' column in the 'Tour_Data.xlsx' table with the 'Tax_Rates.csv' file to apply the correct tax withholding rates. Once you have applied these rates, calculate the net revenue and store it in a new column named 'Net_Revenue_After_Tax'.

Next, we need to handle multi-currency conversions for our regional stakeholders. Please refer to the newly provided 'Currency_Rates_Base_RMB.xlsx' which contains RMB-based exchange rates (e.g., 1 RMB = X Foreign Currency). Your task is to: (1) Derive a USD-to-other-currencies conversion table. (2) Identify the local currency for each 'Country' (e.g., France -> EUR). (3) Convert the values in 'Net_Revenue_After_Tax' (currently in USD) to the local currency. Append these converted results to a new column named 'Local_Currency_Amount'. If a country's currency is not listed in the provided rates, use a 1:1 exchange rate.

In addition to the calculations, please draft a 'Task Completion Summary' as a separate PDF document. In this summary document, you must explicitly document any data anomalies, missing values, or accounting issues you encountered during your analysis and explain how you resolved them. This is critical for our audit trail.

Requirements / Notes
- The final deliverable MUST be an Excel file named 'Music_Tour_PnL_Result.xlsx'.
- The final summary deliverable MUST be a PDF file named 'task_summary.pdf'.
- The overall formatting, style, and layout of all deliverables MUST be clean, professional, and business-ready.
- The derived USD conversion table MUST be included as a separate sheet named 'Derived_USD_Rates' within the final deliverable.