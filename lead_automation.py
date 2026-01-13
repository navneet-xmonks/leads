import requests
import csv
import json
import os
import time
from datetime import datetime, timedelta
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
import pandas as pd

load_dotenv()

# --- Configuration ---
CLIENT_ID = os.getenv('ZOHO_CLIENT_ID')
CLIENT_SECRET = os.getenv('ZOHO_CLIENT_SECRET')
TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"
TOKEN_FILE = "zoho_tokens.json"
LEADS_CSV_FILE = "erickson_leads.csv"
LAST_RUN_FILE = "last_run.json"

# Logging Configuration
VERBOSE_LOGGING = os.getenv('VERBOSE_LOGGING', 'false').lower() == 'true'
MAX_DETAILED_LOGS = int(os.getenv('MAX_DETAILED_LOGS', '5'))  # Max detailed logs before suppressing

# AiSensy Configuration
AISENSY_API_KEY = os.getenv('AISENSY_API_KEY')

# WhatsApp drip tracking
WHATSAPP_DRIP_FILE = "whatsapp_drip.json"
DRIP_CAMPAIGN_NAME = os.getenv("WHATSAPP_DRIP_CAMPAIGN", "Erickson_WhatsApp_Drip")
DRIP_SCHEDULE_UNIT = os.getenv("DRIP_SCHEDULE_UNIT", "days").strip().lower()
TEMPLATE_CAMPAIGNS = {
    1: os.getenv("AISENSY_CAMPAIGN_T1", "Welcome_Erickson"),
    2: os.getenv("AISENSY_CAMPAIGN_T2", "Template_2"),
    3: os.getenv("AISENSY_CAMPAIGN_T3", "Template_3"),
    4: os.getenv("AISENSY_CAMPAIGN_T4", "Template_4"),
    5: os.getenv("AISENSY_CAMPAIGN_T5", "Template_5"),
}
TEMPLATE_MEDIA_URLS = {
    1: "https://www.erickson.co.in/wp-content/uploads/2026/01/Gemini_Generated_Image_2gc1ir2gc1ir2gc1-1-1.png",
    2: "https://xmonks.com/Gemini_Generated_Image_cl9aeicl9aeicl9a%20%281%29.png",
    3: "https://xmonks.com/Gemini_Generated_Image_j1tessj1tessj1te%20%281%29.png",
    4: "https://www.xmonks.com/Gemini_Generated_Image_f8q9dsf8q9dsf8q9%20%281%29.png",
    5: "https://xmonks.com/Gemini_Generated_Image_4o47sw4o47sw4o47%20%281%29.png",
}
DRIP_SCHEDULE_DAYS = {1: 0, 2: 1, 3: 4, 4: 5, 5: 7}
DRIP_SCHEDULE_MINUTES = {1: 0, 2: 1, 3: 2, 4: 3, 5: 5}

class LeadAutomation:
    def __init__(self):
        self.leads_csv_headers = [
            'id', 'first_name', 'last_name', 'email', 'phone', 
            'lead_source', 'referral_code', 'referral_status', 'record_status', 
            'created_time', 'modified_time', 'fetched_at', 'message_sent'
        ]

    def get_template_campaign(self, step):
        """Get the AiSensy campaign name for a drip step."""
        return TEMPLATE_CAMPAIGNS.get(step, "")

    def get_template_media(self, step):
        """Get the media URL and filename for a drip step."""
        media_url = TEMPLATE_MEDIA_URLS.get(step, "")
        if not media_url:
            return "", ""

        parsed = urlparse(media_url)
        filename = unquote(os.path.basename(parsed.path))
        return media_url, filename

    def is_message_success(self, response):
        """Determines if a WhatsApp message send was successful."""
        return (
            response.get('success') == 'true'
            or response.get('status') == 'success'
            or response.get('status_code') == 200
        )

    def build_processed_lead(self, lead, fetched_at, message_sent_value, phone=None):
        """Builds a CSV-ready lead row from Zoho lead data."""
        if phone is None:
            phone = lead.get('Mobile') or lead.get('Phone')
            phone = self.normalize_phone_number(phone)

        return {
            'id': lead.get('id'),
            'first_name': lead.get('First_Name', ''),
            'last_name': lead.get('Last_Name', ''),
            'email': lead.get('Email', ''),
            'phone': phone,
            'lead_source': lead.get('Lead_Source', ''),
            'referral_code': lead.get('Referral_Code', ''),
            'referral_status': lead.get('Referral_Status', ''),
            'record_status': lead.get('Record_Status__s', ''),
            'created_time': lead.get('Created_Time', ''),
            'modified_time': lead.get('Modified_Time', ''),
            'fetched_at': fetched_at,
            'message_sent': message_sent_value
        }

    def append_processed_leads(self, processed_leads):
        """Append processed leads to the CSV with headers if needed."""
        if not processed_leads:
            return

        file_exists = os.path.exists(LEADS_CSV_FILE)
        with open(LEADS_CSV_FILE, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.leads_csv_headers)
            if not file_exists:
                writer.writeheader()
            writer.writerows(processed_leads)

        print(f"✅ {len(processed_leads)} leads saved to {LEADS_CSV_FILE}")

    def load_drip_entries(self):
        """Load the WhatsApp drip tracking entries from JSON."""
        if not os.path.exists(WHATSAPP_DRIP_FILE):
            return []

        try:
            with open(WHATSAPP_DRIP_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            print(f"⚠️ Error loading drip file: {e}")
            return []

    def save_drip_entries(self, entries):
        """Save WhatsApp drip tracking entries to JSON."""
        try:
            with open(WHATSAPP_DRIP_FILE, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=2)
        except Exception as e:
            print(f"❌ Error saving drip file: {e}")

    def calculate_next_send_at(self, t1_sent_at, step):
        """Calculate next send time based on Template 1 send time."""
        if isinstance(t1_sent_at, str):
            try:
                t1_sent_at = datetime.fromisoformat(t1_sent_at)
            except Exception:
                return None
        schedule_unit = DRIP_SCHEDULE_UNIT or "days"

        if schedule_unit == "minutes":
            minutes_offset = DRIP_SCHEDULE_MINUTES.get(step)
            if minutes_offset is None:
                return None
            return (t1_sent_at + timedelta(minutes=minutes_offset)).isoformat()

        days_offset = DRIP_SCHEDULE_DAYS.get(step)
        if days_offset is None:
            return None
        return (t1_sent_at + timedelta(days=days_offset)).isoformat()

    def add_to_drip_queue(self, drip_entries):
        """Add new entries to the drip queue, avoiding duplicates by phone."""
        if not drip_entries:
            return

        existing_entries = self.load_drip_entries()
        existing_by_phone = {entry.get('phone'): entry for entry in existing_entries}

        added_count = 0
        for entry in drip_entries:
            phone = entry.get('phone')
            if not phone or phone in existing_by_phone:
                continue
            existing_entries.append(entry)
            existing_by_phone[phone] = entry
            added_count += 1

        if added_count:
            self.save_drip_entries(existing_entries)
            print(f"✅ Added {added_count} numbers to drip queue")

    def process_drip_queue(self):
        """Send due drip templates and update the queue."""
        entries = self.load_drip_entries()
        if not entries:
            return

        now = datetime.now()
        updated_entries = []
        completed_count = 0
        sent_count = 0
        due_count = 0

        for entry in entries:
            next_step = entry.get('next_step')
            if next_step is None:
                last_step = entry.get('last_step_sent', 1)
                next_step = last_step + 1

            if next_step > 5:
                completed_count += 1
                continue

            next_send_at = entry.get('next_send_at')
            if not next_send_at:
                next_send_at = self.calculate_next_send_at(entry.get('t1_sent_at'), next_step)
                entry['next_send_at'] = next_send_at

            try:
                next_send_dt = datetime.fromisoformat(next_send_at) if next_send_at else None
            except Exception:
                next_send_dt = None

            if next_send_dt and next_send_dt <= now:
                due_count += 1
                campaign_name = self.get_template_campaign(next_step)
                media_url, media_filename = self.get_template_media(next_step)
                phone = entry.get('phone')
                first_name = entry.get('first_name', 'Friend')
                user_name = f"{first_name} {entry.get('last_name', '')}".strip()

                if not phone or not campaign_name or not media_url:
                    updated_entries.append(entry)
                    continue

                response = self.send_aisensy_message(
                    phone=phone,
                    user_name=user_name,
                    campaign_name=campaign_name,
                    media_url=media_url,
                    media_filename=media_filename,
                    template_params=[first_name]
                )

                if self.is_message_success(response):
                    sent_count += 1
                    entry['last_step_sent'] = next_step
                    entry['last_sent_at'] = now.isoformat()
                    entry['last_campaign'] = campaign_name

                    if next_step >= 5:
                        completed_count += 1
                        continue

                    next_step = next_step + 1
                    entry['next_step'] = next_step
                    entry['next_send_at'] = self.calculate_next_send_at(entry.get('t1_sent_at'), next_step)
                    entry['next_campaign'] = self.get_template_campaign(next_step)
                else:
                    # Keep entry unchanged to retry on next run
                    pass

            updated_entries.append(entry)

        if sent_count or completed_count or len(updated_entries) != len(entries):
            self.save_drip_entries(updated_entries)
            if sent_count:
                print(f"✅ Drip messages sent: {sent_count}")
            if due_count and sent_count < due_count:
                print(f"⚠️ Drip messages failed: {due_count - sent_count}")
            if completed_count:
                print(f"✅ Drip entries completed: {completed_count}")
    
    def is_first_run(self):
        """Check if this is the first time running the automation."""
        return not os.path.exists(LEADS_CSV_FILE)
    
    def save_last_run_time(self):
        """Save the current time as last run time."""
        try:
            current_time = datetime.now().isoformat()
            with open(LAST_RUN_FILE, 'w') as f:
                json.dump({'last_run': current_time}, f, indent=2)
            print(f"✅ Last run time saved: {current_time}")
        except Exception as e:
            print(f"❌ Error saving last run time: {e}")
            # Still create the file even if there's an error
            try:
                with open(LAST_RUN_FILE, 'w') as f:
                    f.write('{"last_run": "' + datetime.now().isoformat() + '"}')
                print("✅ Fallback: Last run file created")
            except Exception as e2:
                print(f"❌ Critical error creating last run file: {e2}")
    
    def get_last_run_time(self):
        """Get the last run time."""
        if os.path.exists(LAST_RUN_FILE):
            try:
                with open(LAST_RUN_FILE, 'r') as f:
                    data = json.load(f)
                    return datetime.fromisoformat(data['last_run'])
            except:
                pass
        return None
        
    def load_environment_tokens(self):
        """Loads tokens from environment variables (for GitHub Actions)."""
        print("🔍 Loading tokens from environment variables...")
        
        client_id = os.getenv('ZOHO_CLIENT_ID')
        client_secret = os.getenv('ZOHO_CLIENT_SECRET')
        refresh_token = os.getenv('ZOHO_REFRESH_TOKEN')
        api_domain = os.getenv('ZOHO_API_DOMAIN')
        
        print(f"   ZOHO_CLIENT_ID: {'✅ Set' if client_id else '❌ Missing'}")
        print(f"   ZOHO_CLIENT_SECRET: {'✅ Set' if client_secret else '❌ Missing'}")
        print(f"   ZOHO_REFRESH_TOKEN: {'✅ Set' if refresh_token else '❌ Missing'}")
        print(f"   ZOHO_API_DOMAIN: {'✅ Set' if api_domain else '❌ Missing'}")
        
        if client_id and client_secret and refresh_token and api_domain:
            return {
                'client_id': client_id,
                'client_secret': client_secret,
                'refresh_token': refresh_token,
                'api_domain': api_domain
            }
        else:
            print("❌ Some required environment variables are missing")
            return None

    def load_tokens(self):
        """Loads tokens from environment variables (GitHub Actions) or JSON file (local)."""
        # First try environment variables (for GitHub Actions)
        env_tokens = self.load_environment_tokens()
        if env_tokens:
            return env_tokens
        
        # Fall back to JSON file (for local development)
        try:
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, 'r') as f:
                    return json.load(f)
            else:
                print(f"❌ Token file {TOKEN_FILE} not found")
                return {}
        except Exception as e:
            print(f"❌ Error loading tokens: {str(e)}")
            return {}

    def save_tokens(self, token_data):
        """Saves the relevant tokens to the JSON file with timestamp."""
        current_time = datetime.now().isoformat()
        data_to_save = {
            'access_token': token_data.get('access_token'),
            'access_token_timestamp': current_time,
            'refresh_token': token_data.get('refresh_token'),
            'api_domain': token_data.get('api_domain')
        }
        with open(TOKEN_FILE, 'w') as f:
            json.dump(data_to_save, f, indent=4)
        print(f"✅ Tokens saved to {TOKEN_FILE} at {current_time}")

    def is_access_token_valid(self, stored_tokens):
        """Check if the stored access token is still valid (within 55 minutes of creation)."""
        access_token = stored_tokens.get('access_token')
        timestamp_str = stored_tokens.get('access_token_timestamp')
        
        if not access_token or not timestamp_str:
            return False
        
        try:
            token_time = datetime.fromisoformat(timestamp_str)
            current_time = datetime.now()
            
            # Check if token is less than 55 minutes old (5 minute buffer before 1-hour expiry)
            time_diff = current_time - token_time
            if time_diff.total_seconds() < 3300:  # 55 minutes = 3300 seconds
                minutes_old = int(time_diff.total_seconds() / 60)
                print(f"✅ Access token is still valid ({minutes_old} minutes old)")
                return True
            else:
                minutes_old = int(time_diff.total_seconds() / 60)
                print(f"⏰ Access token expired ({minutes_old} minutes old)")
                return False
                
        except Exception as e:
            print(f"❌ Error checking token timestamp: {e}")
            return False

    def refresh_access_token(self, refresh_token):
        """Refreshes the Zoho API access token using the refresh token."""
        client_id = os.getenv('ZOHO_CLIENT_ID')
        client_secret = os.getenv('ZOHO_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            print("❌ Missing ZOHO_CLIENT_ID or ZOHO_CLIENT_SECRET environment variables")
            return None
        
        token_url = "https://accounts.zoho.com/oauth/v2/token"
        
        data = {
            'refresh_token': refresh_token,
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'refresh_token'
        }
        
        print(f"🔄 Making token refresh request to {token_url}")
        print(f"   Using client_id: {client_id[:8]}..." if client_id else "   No client_id")
        print(f"   Using refresh_token: {refresh_token[:8]}..." if refresh_token else "   No refresh_token")
        
        try:
            response = requests.post(token_url, data=data)
            print(f"   Response status: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                print("✅ Token refresh successful")
                return token_data
            else:
                print(f"❌ Token refresh failed: {response.status_code}")
                print(f"   Response: {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error refreshing token: {str(e)}")
            return None

    def get_valid_token_data(self):
        """Gets valid token data for Zoho API calls - only refresh if needed."""
        stored_tokens = self.load_tokens()
        refresh_token = stored_tokens.get('refresh_token')
        
        if not refresh_token:
            print("❌ No refresh token found. Please check ZOHO_REFRESH_TOKEN secret.")
            print("💡 Make sure you have set the following GitHub Secrets:")
            print("   - ZOHO_CLIENT_ID")
            print("   - ZOHO_CLIENT_SECRET") 
            print("   - ZOHO_REFRESH_TOKEN")
            print("   - ZOHO_API_DOMAIN")
            return None
        
        # Always try to refresh the access token for GitHub Actions to ensure it's valid
        print("🔄 Refreshing access token for reliability...")
        token_data = self.refresh_access_token(refresh_token)
        
        if token_data and 'access_token' in token_data:
            if 'api_domain' in token_data:
                self.save_tokens(token_data)
            else:
                # Use stored api_domain if not in response
                token_data['api_domain'] = stored_tokens.get('api_domain')
                self.save_tokens(token_data)
            return token_data
        else:
            print("❌ Failed to obtain valid access token")
            print("💡 This usually means:")
            print("   1. ZOHO_REFRESH_TOKEN is invalid or expired")
            print("   2. ZOHO_CLIENT_ID or ZOHO_CLIENT_SECRET is wrong")
            print("   3. Your Zoho OAuth app needs to be re-authorized")
            return None

    def fetch_zoho_leads(self, access_token, api_domain):
        """Fetches leads from Zoho CRM with phone numbers - filtered by specific Lead Sources."""
        target_sources = ["Google Landing Page", "Form Submission", "Youtube Ads"]
        print(f"📞 Fetching leads from Zoho CRM (Lead Sources: {', '.join(target_sources)})...")

        headers = {
            'Authorization': f'Zoho-oauthtoken {access_token}'
        }
        
        # Include phone field and other important fields + Lead_Source
        fields = "First_Name,Last_Name,Email,Phone,Mobile,Lead_Source,Referral_Code,Referral_Status,Record_Status__s,Created_Time,Modified_Time"
        
        # Try different formats for Zoho criteria
        # Method 1: Simple format without URL encoding
        url = f"{api_domain}/crm/v8/Leads?fields={fields}&criteria=Lead_Source:equals:Google Landing Page&per_page=200"

        try:
            print(f"🔍 API URL: {url}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            leads_data = response.json()
            leads = leads_data.get('data', [])
            
            # If no leads found with simple criteria, try alternative format
            if not leads:
                print("🔄 Trying alternative criteria format...")
                # Method 2: Try fetching all and filter manually
                url2 = f"{api_domain}/crm/v8/Leads?fields={fields}&per_page=200"
                response2 = requests.get(url2, headers=headers)
                response2.raise_for_status()
                leads_data2 = response2.json()
                leads = leads_data2.get('data', [])
            
            # If still no leads, try search API
            if not leads:
                print("🔄 Trying COQL search API...")
                search_url = f"{api_domain}/crm/v8/coql"
                coql_query = {
                    "select_query": f"select {fields} from Leads where Lead_Source in ('Google Landing Page', 'Form Submission', 'Youtube Ads') limit 200"
                }
                search_response = requests.post(search_url, headers=headers, json=coql_query)
                if search_response.status_code == 200:
                    search_data = search_response.json()
                    leads = search_data.get('data', [])
            
            # Debug: Print lead sources if any found
            if leads:
                print("🔍 Sample lead sources from response:")
                for i, lead in enumerate(leads[:3]):
                    lead_source = lead.get('Lead_Source', 'No Lead_Source')
                    first_name = lead.get('First_Name', 'No Name')
                    print(f"  Lead {i+1}: {first_name} - Lead_Source = '{lead_source}'")
            
            # Apply manual filter to ensure only target leads (since API filtering seems inconsistent)
            if leads:
                target_leads = []
                for lead in leads:
                    lead_source = lead.get('Lead_Source', '')
                    if lead_source is None:
                        lead_source = ''
                    if lead_source in target_sources:
                        target_leads.append(lead)
                
                print(f"🔍 Manual filtering: {len(target_leads)} target leads out of {len(leads)} fetched")
                leads = target_leads
            
            print(f"✅ Final result: {len(leads)} leads with Lead_Source in {target_sources}")
            return leads

        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching leads from Zoho: {e}")
            if hasattr(e, 'response') and e.response:
                print(f"❌ Response: {e.response.text}")
            return []

    def normalize_phone_number(self, phone):
        """Normalizes phone number to international format."""
        if not phone:
            return None
            
        # Remove all non-digit characters
        phone = ''.join(filter(str.isdigit, phone))
        
        # Add +91 for Indian numbers if not present
        if len(phone) == 10:
            # 10 digits: assume Indian mobile number
            phone = f"+91{phone}"
        elif len(phone) == 11 and phone.startswith('9'):
            # 11 digits starting with 9: likely missing the '1' in '91'
            phone = f"+91{phone}"
        elif len(phone) == 12 and phone.startswith('91'):
            # 12 digits starting with 91: add + prefix
            phone = f"+{phone}"
        elif len(phone) == 13 and phone.startswith('91'):
            # 13 digits starting with 91: add + prefix (already has country code)
            phone = f"+{phone}"
        elif not phone.startswith('+'):
            # For any other case, add + prefix
            phone = f"+{phone}"
            
        return phone

    def save_leads_to_csv(self, leads, message_sent_value='No'):
        """Saves leads to CSV file with timestamp - ONLY test leads."""
        current_time = datetime.now().isoformat()
        processed_leads = []
        target_sources = ["Google Landing Page", "Form Submission", "Youtube Ads"]

        for lead in leads:
            # FILTER: Only save leads with target Lead Sources
            lead_source = lead.get('Lead_Source', '')
            if lead_source is None:
                lead_source = ''

            if lead_source not in target_sources:
                print(f"⚠️ Skipping lead {lead.get('First_Name', 'Unknown')} - Lead_Source is '{lead.get('Lead_Source', 'None')}', not in target sources")
                continue

            processed_leads.append(
                self.build_processed_lead(
                    lead,
                    fetched_at=current_time,
                    message_sent_value=message_sent_value
                )
            )

        self.append_processed_leads(processed_leads)
        return processed_leads

    def get_existing_lead_ids(self):
        """Get list of existing lead IDs from CSV to compare."""
        if not os.path.exists(LEADS_CSV_FILE):
            return set()
        
        try:
            df = pd.read_csv(LEADS_CSV_FILE)
            return set(df['id'].astype(str).tolist())
        except Exception as e:
            print(f"❌ Error reading existing CSV: {e}")
            return set()

    def get_new_leads_from_last_6_hours(self):
        """Gets leads that were created in the last 6 hours."""
        if not os.path.exists(LEADS_CSV_FILE):
            print("📝 No existing CSV file found. All leads will be considered new.")
            return []
        
        try:
            df = pd.read_csv(LEADS_CSV_FILE)
            
            # Convert created_time to datetime
            df['created_time'] = pd.to_datetime(df['created_time'], errors='coerce')
            
            # Get leads from last 6 hours
            six_hours_ago = datetime.now() - timedelta(hours=6)
            recent_leads = df[df['created_time'] >= six_hours_ago]
            
            # Remove duplicates based on email or phone
            recent_leads = recent_leads.drop_duplicates(subset=['email', 'phone'], keep='last')
            
            print(f"🔍 Found {len(recent_leads)} new leads from last 6 hours")
            return recent_leads.to_dict('records')
            
        except Exception as e:
            print(f"❌ Error processing CSV: {e}")
            return []

    def find_new_leads(self, current_leads):
        """Compare current leads with existing CSV to find new ones - optimized for large datasets."""
        existing_ids = self.get_existing_lead_ids()
        
        new_leads = []
        total_leads = len(current_leads)
        
        print(f"🔍 Checking {total_leads} leads against {len(existing_ids)} existing records...")
        
        for i, lead in enumerate(current_leads, 1):
            lead_id = str(lead.get('id', ''))
            if lead_id not in existing_ids:
                new_leads.append(lead)
            
            # Progress update for large datasets
            if total_leads > 1000 and i % 500 == 0:
                print(f"📊 Progress: {i}/{total_leads} leads checked...")
        
        print(f"🆕 Found {len(new_leads)} new leads to process")
        
        # Alert for large new lead counts
        if len(new_leads) > 100:
            print(f"⚠️ LARGE BATCH: {len(new_leads)} new leads detected - this may take a while to process")
            
        return new_leads

    def send_aisensy_message(self, phone, user_name, campaign_name, media_url, media_filename, template_params=None):
        """Sends a WhatsApp message via AiSensy API."""
        url = "https://backend.aisensy.com/campaign/t1/api/v2"

        payload = {
            "apiKey": AISENSY_API_KEY,
            "campaignName": campaign_name,
            "destination": phone,
            "userName": user_name,
            "source": "Zoho CRM Automation",
            "media": {
                "url": media_url,
                "filename": media_filename
            },
            "templateParams": template_params or []
        }

        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, json=payload, headers=headers)
            return response.json()
        except Exception as e:
            return {"status_code": 0, "error": str(e)}

    def send_welcome_messages_to_new_leads(self, new_leads):
        """Sends Template 1 to new leads, saves successes, and queues drip sends."""
        if not new_leads:
            print("📱 No new leads to send messages to.")
            return

        successful_sends = 0
        failed_sends = 0
        no_phone_skips = 0
        skipped_sends = 0

        processed_leads = []
        drip_entries = []
        target_sources = ["Google Landing Page", "Form Submission", "Youtube Ads"]
        campaign_name = self.get_template_campaign(1)
        media_url, media_filename = self.get_template_media(1)

        if not campaign_name or not media_url:
            print("❌ Missing campaign name for Template 1")
            return

        print(f"📱 Processing {len(new_leads)} leads for Template 1...")

        for i, lead in enumerate(new_leads, 1):
            lead_source = lead.get('Lead_Source', '')
            if lead_source is None:
                lead_source = ''

            if lead_source not in target_sources:
                skipped_sends += 1
                continue

            phone = lead.get('Mobile') or lead.get('Phone')
            phone = self.normalize_phone_number(phone)
            first_name = lead.get('First_Name', 'Friend')

            if not phone:
                no_phone_skips += 1
                if no_phone_skips <= 3:
                    print(f"⚠️ Skipping {first_name} - no phone number")
                elif no_phone_skips == 4:
                    print("⚠️ ... more leads without phone numbers (suppressing further logs)")
                continue

            print(f"📱 [{i}/{len(new_leads)}] Sending Template 1 to {first_name} ({phone})")

            response = self.send_aisensy_message(
                phone=phone,
                user_name=f"{first_name} {lead.get('Last_Name', '')}".strip(),
                campaign_name=campaign_name,
                media_url=media_url,
                media_filename=media_filename,
                template_params=[first_name]
            )

            if self.is_message_success(response):
                successful_sends += 1
                sent_at = datetime.now().isoformat()
                processed_leads.append(
                    self.build_processed_lead(
                        lead,
                        fetched_at=sent_at,
                        message_sent_value='Yes',
                        phone=phone
                    )
                )

                next_step = 2
                drip_entries.append({
                    'phone': phone,
                    'lead_id': str(lead.get('id', '')),
                    'first_name': lead.get('First_Name', ''),
                    'last_name': lead.get('Last_Name', ''),
                    'drip_campaign': DRIP_CAMPAIGN_NAME,
                    't1_sent_at': sent_at,
                    'last_step_sent': 1,
                    'next_step': next_step,
                    'next_send_at': self.calculate_next_send_at(sent_at, next_step),
                    'next_campaign': self.get_template_campaign(next_step)
                })
                print(f"✅ Template 1 sent successfully to {first_name}")
            else:
                failed_sends += 1
                if failed_sends <= 5:
                    print(f"❌ Failed to send Template 1 to {first_name}: {response}")
                elif failed_sends == 6:
                    print("❌ ... more failures (suppressing detailed error logs)")

            time.sleep(2)

            if i % 50 == 0:
                print(f"📊 Progress: {i}/{len(new_leads)} leads processed...")

        if processed_leads:
            self.append_processed_leads(processed_leads)
            self.add_to_drip_queue(drip_entries)

        print("\n📊 Template 1 Summary:")
        print(f"✅ Successfully sent: {successful_sends}")
        print(f"❌ Failed to send: {failed_sends}")
        print(f"⚠️ Skipped (no phone): {no_phone_skips}")
        print(f"⏭️ Skipped (filtered): {skipped_sends}")
        print(f"📱 Total processed: {len(new_leads)}")
    
    def update_message_status_in_csv(self, leads_with_status):
        """Update the CSV file with message sent status for the leads."""
        if not os.path.exists(LEADS_CSV_FILE):
            return
        
        try:
            # First, check if CSV needs the message_sent column
            df_test = pd.read_csv(LEADS_CSV_FILE, nrows=1)
            if 'message_sent' not in df_test.columns:
                print("🔧 CSV missing 'message_sent' column, fixing structure...")
                self.fix_csv_structure()
            
            # Now read the full CSV
            df = pd.read_csv(LEADS_CSV_FILE)
            print(f"✅ Read CSV with {len(df)} valid rows and {len(df.columns)} columns")
            
            # Ensure message_sent column exists
            if 'message_sent' not in df.columns:
                df['message_sent'] = 'No'
                print("✅ Added missing 'message_sent' column")
            
            # Update message status for each lead
            for lead in leads_with_status:
                lead_id = str(lead.get('id', ''))
                message_status = lead.get('message_sent', 'No')
                
                # Update the specific lead's message status
                df.loc[df['id'].astype(str) == lead_id, 'message_sent'] = message_status
            
            # Save updated CSV
            df.to_csv(LEADS_CSV_FILE, index=False)
            print(f"✅ Updated message status in CSV for {len(leads_with_status)} leads")
            
        except Exception as e:
            print(f"❌ Error updating message status in CSV: {e}")
            print("🔧 Attempting to recover by fixing CSV structure...")
            try:
                self.fix_csv_structure()
                print("✅ CSV structure fixed, please retry the operation")
            except Exception as fix_error:
                print(f"❌ Failed to fix CSV structure: {str(fix_error)}")

    def fix_csv_structure(self):
        """Fixes CSV structure by adding missing message_sent column if needed."""
        print("🔧 Fixing CSV structure...")
        
        try:
            # Read file line by line and fix issues
            with open(LEADS_CSV_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            if not lines:
                print("❌ CSV file is empty")
                return
            
            # Check header
            header = lines[0].strip()
            
            # Check if message_sent column is missing
            if 'message_sent' not in header:
                print("✅ Adding missing 'message_sent' column to header")
                header += ',message_sent'
                lines[0] = header + '\n'
                
                # Add 'No' to all existing data lines for the new column
                for i in range(1, len(lines)):
                    if lines[i].strip():  # Only process non-empty lines
                        lines[i] = lines[i].strip() + ',No\n'
            
            # Write the updated CSV
            with open(LEADS_CSV_FILE, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            print(f"✅ Fixed CSV structure: {len(lines)-1} data rows updated")
                
        except Exception as e:
            print(f"❌ Error fixing CSV structure: {str(e)}")
            raise

    def run_automation(self):
        """Main automation function - simple flow for testing."""
        print("🚀 Starting Lead Automation Process...")
        print("=" * 50)
        
        # Check if this is first run
        first_run = self.is_first_run()
        if first_run:
            print("🎯 FIRST RUN: Will fetch and save leads, but won't send messages")
        else:
            print("🔄 SUBSEQUENT RUN: Will check for new leads and send messages")
        
        # 1. Get valid tokens
        token_data = self.get_valid_token_data()
        if not token_data:
            return
        
        # 2. Fetch leads from Zoho
        leads = self.fetch_zoho_leads(
            access_token=token_data.get('access_token'),
            api_domain=token_data.get('api_domain')
        )
        
        if not leads:
            print("❌ No leads fetched. Exiting.")
            return
        
        # 3. If not first run, find new leads
        if not first_run:
            new_leads = self.find_new_leads(leads)
            
            if new_leads:
                # Send Template 1 and only save leads after success
                self.send_welcome_messages_to_new_leads(new_leads)
            else:
                print("📱 No new leads found.")
        else:
            # First run - save all leads to CSV
            self.save_leads_to_csv(leads)
            print("📝 First run completed. Next run will check for new leads and send messages.")

        # Process drip queue every run
        self.process_drip_queue()
        
        # Save last run time for tracking
        try:
            self.save_last_run_time()
        except Exception as e:
            print(f"⚠️ Warning: Could not save last run time: {e}")
        
        # Double-check that last_run.json exists
        if not os.path.exists(LAST_RUN_FILE):
            print("⚠️ Last run file missing, creating backup...")
            try:
                with open(LAST_RUN_FILE, 'w') as f:
                    json.dump({'last_run': datetime.now().isoformat(), 'backup': True}, f)
                print("✅ Backup last run file created")
            except Exception as e:
                print(f"❌ Failed to create backup last run file: {e}")
        
        print("\n🎉 Automation process completed!")
        print("=" * 50)

if __name__ == "__main__":
    automation = LeadAutomation()
    
    # Check if CSV needs fixing (add message_sent column if missing)
    if os.path.exists(LEADS_CSV_FILE):
        try:
            # Try to read the CSV to see if it has message_sent column
            df_check = pd.read_csv(LEADS_CSV_FILE, nrows=1)
            
            if 'message_sent' not in df_check.columns:
                print("🔧 Adding missing 'message_sent' column to existing CSV...")
                automation.fix_csv_structure()
                print("✅ CSV structure updated!")
            else:
                print("✅ CSV structure is correct")
                
        except Exception as e:
            print(f"⚠️ CSV check error: {e}")
    
    automation.run_automation()
