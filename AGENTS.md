# AGENTS Instructions

## Project summary
- Python automation that pulls Zoho CRM leads, filters by Lead_Source, stores CSV history, and sends WhatsApp messages via AiSensy with a drip schedule.
- Primary entrypoint: lead_automation.py

## Setup
- Python 3.12 recommended.
- Install deps: `python3 -m pip install -r requirements.txt`

## Required environment variables
- ZOHO_CLIENT_ID
- ZOHO_CLIENT_SECRET
- ZOHO_REFRESH_TOKEN
- ZOHO_API_DOMAIN (example: https://www.zohoapis.com)
- AISENSY_API_KEY
- Optional: AISENSY_CAMPAIGN_T1..T5 (defaults to Template_2..5 and Welcome_Erickson for T1)
- Optional: WHATSAPP_DRIP_CAMPAIGN (default Erickson_WhatsApp_Drip)
- Optional: VERBOSE_LOGGING=true, MAX_DETAILED_LOGS=5

## Running locally
- `python3 lead_automation.py`
- First run writes the CSV and does not send messages.
- Subsequent runs send Template 1 to new leads, then schedule Templates 2-5 via the drip queue.

## Data files
- erickson_leads.csv: lead history and Template 1 status.
- last_run.json: last successful run timestamp.
- zoho_tokens.json: cached tokens when not using env vars.
- whatsapp_drip.json: drip queue for Templates 2-5.

## Notes for changes
- Lead filtering is by Lead_Source in `fetch_zoho_leads` and `save_leads_to_csv`.
- Phone normalization assumes India (+91) for 10-digit numbers.
- Messaging uses AiSensy campaign names from `AISENSY_CAMPAIGN_T1..T5` and a fixed image URL.
