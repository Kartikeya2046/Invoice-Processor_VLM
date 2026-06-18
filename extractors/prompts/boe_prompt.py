BOE_EXTRACTION_PROMPT: str = """
Please examine the bill of entry (BOE) image carefully and locate each field by scanning for any of its known aliases — not just the canonical name.

Alias Map:
- boe_number: "BOE Number, BE Number, Bill of Entry No, Bill of Entry Number, B/E No, Entry No, Customs Entry No"
- boe_date: "BOE Date, BE Date, Bill of Entry Date, Date of Entry, Entry Date, Assessment Date"
- igst: "IGST, Integrated GST, Integrated Tax, IG Tax"
- cust_duty: "Customs Duty, Custom Duty, Cust. Duty, BCD, Basic Customs Duty, Import Duty, Assessable Duty"
- sbcess: "SBCESS, SB Cess, Social Welfare Surcharge, SWS, Surcharge, SW Surcharge"

Extraction Rules:
1. For each field: if found under any alias, extract the value and map it to the canonical key. If genuinely not present in the document, return null for that key.
2. boe_date must be normalized to ISO 8601 (YYYY-MM-DD) regardless of how it appears in the document (e.g. 12/03/2024, 12-Mar-24, March 12 2024).
3. Numerics (igst, cust_duty, sbcess) must be numeric — strip currency symbols, commas, and units.

**sbcess**
- SBCESS (Social Welfare Surcharge) is always calculated as 10% of Basic Customs Duty (BCD/Cust. Duty).
- It is always a smaller value than cust_duty. If the value you found for sbcess is equal to or greater than cust_duty, you have extracted the wrong field — look again.
- Example: if cust_duty is 35145.00, then sbcess should be approximately 3514.50 (10% of 35145.00).
- Do NOT confuse sbcess with cust_duty — they are always listed as separate line items.

4. Return ONLY a valid JSON object with exactly these 5 keys: boe_number, boe_date, igst, cust_duty, sbcess. No markdown fences, no explanation, no extra keys.
"""
