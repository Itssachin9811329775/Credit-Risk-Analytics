# Stage 5: exploratory analysis

Generated from validated UCI 350 data. Status: **passed**.
Run time (UTC): 2026-11-03T04:36:56.663283+00:00.

- Customers: 30,000; next-month defaults: 6,636 (22.12%).
- September status of two or more months' documented delay: 2,177 defaults among 3,130 customers (69.55%).
- September paid-duly code -1: 954 defaults among 5,686 customers (16.78%).
- One-month delay code 1 occurs for 28 customers in August versus 3,688 in September. Review timing and coding before interpreting the status-share change as deterioration.
- Seven PNG charts were generated in `reports/figures/`; their hashes and all plotted segment values are recorded in `reports/eda_summary.json`.

All customer-level rates count each customer once. Error bars use 95% Wilson
binomial intervals; they summarize sampling uncertainty under a binomial model,
not dataset representativeness, causal effects, or future portfolio performance.
Monthly status shares use 30,000 customers separately in each month. Transition
shares condition on the August category, with counts shown in every cell.

Undocumented codes remain separate. Zero documented-delay months do not imply
six on-time payments; zero recorded payments do not establish missed payments.
These are descriptive associations in historical Taiwanese credit-card data,
not Finnable customers. See `docs/stage_05_eda.md` for interpretation and commands.
