```json
{
  "Name": "US E-commerce Order Duty Processing and Summary",
  "Description": "Process last month's e-commerce orders to calculate estimated duties for US customers, clean the order amount data, and generate a processed dataset along with a PDF task summary.",
  "Key_Steps": [
    "Load the initial dataset from 'ecommerce_orders_last_month.csv'.",
    "Filter the records to include only those where the 'user_country' is equal to 'USA'.",
    "Identify and handle any missing values in the 'order_amount' column.",
    "Identify negative values in the 'order_amount' column and convert them to their absolute values.",
    "Create a new column named 'estimated_duty' by multiplying the cleaned 'order_amount' by 0.08.",
    "Export the final processed dataset to a file named 'Processed_US_Duty_Report.csv'.",
    "Draft a 'Task Completion Summary' detailing the operations performed and save it as a separate PDF document strictly named 'task_summary.pdf'."
  ],
  "Data_Requirements": [
    "Input: 'ecommerce_orders_last_month.csv'",
    "Output: 'Processed_US_Duty_Report.csv'",
    "Output: 'task_summary.pdf'"
  ]
}
```

### Critical Auto-Appended Constraints:
- The final summary MUST be named 'task_summary.pdf'.
