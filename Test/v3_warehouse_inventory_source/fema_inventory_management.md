# FEMA inventory management — workflow and data evidence

Source publisher: U.S. Federal Emergency Management Agency.
Source URL: https://www.fema.gov/sites/default/files/documents/fema_distribution-management-plan-guide-2.0.pdf
Source location: Distribution Management Plan Guide 2.0, Appendix F, Inventory Management Form, page 53.
Retrieved: 2026-07-10.
Use: short attributed structural summary for public-source skill extraction; no GDPVal material is present.

The FEMA inventory management form tracks an incident, date, product identifier, product description, cost, initial quantity intake, inbound origin or location, initial quantity outtake, and outbound destination or location. Inventory status therefore depends on both quantity movement and location information.

Deterministic inventory rule: ending quantity equals opening quantity plus accepted inbound quantity minus authorized outbound quantity. A validation task should compare that calculated balance with the recorded location balance and keep any mismatch unresolved until supporting records explain it.

Receiving rule: compare the purchase order or expected record, shipment manifest, and receiving record by shipment ID and item ID. Classify differences as matched, shortage, overage, damaged, wrong item, location discrepancy, or unresolved. Do not update usable inventory for damaged or unidentified items until the provided handling rule permits acceptance.

Supervisor report: summarize verified inventory status, list every exception with its evidence ID and rule basis, and state the required hold, correction, escalation, or acceptance action. The report must not invent missing shipment facts or rules.
