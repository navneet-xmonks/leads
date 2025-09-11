import requests
import csv
import json
import os
import time
from datetime import datetime, timedelta
import pandas as pd

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
CAMPAIGN_NAME = "welcome_test"
WELCOME_IMAGE_URL = "https://xmonks.com/5eb66e6a-4335-4b78-8279-7c9298332add.jpg"
IMAGE_FILENAME = "5eb66e6a-4335-4b78-8279-7c9298332add.jpg"

class LeadAutomation:
    def __init__(self):
        self.leads_csv_headers = [
            'id', 'first_name', 'last_name', 'email', 'phone', 
            'lead_source', 'referral_code', 'referral_status', 'record_status', 
            'created_time', 'modified_time', 'fetched_at', 'message_sent'
        ]
    
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
        target_sources = ["Google Landing Page", "Form Submission", "Whatsapp Marketing"]
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
                    "select_query": f"select {fields} from Leads where Lead_Source in ('Google Landing Page', 'Form Submission', 'Whatsapp Marketing') limit 200"
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
            phone = f"+91{phone}"
        elif len(phone) == 12 and phone.startswith('91'):
            phone = f"+{phone}"
        elif not phone.startswith('+'):
            phone = f"+{phone}"
            
        return phone

    def save_leads_to_csv(self, leads):
        """Saves leads to CSV file with timestamp - ONLY test leads."""
        current_time = datetime.now().isoformat()
        
        # Check if CSV exists to determine if we need headers
        file_exists = os.path.exists(LEADS_CSV_FILE)
        
        processed_leads = []
        target_sources = ["Google Landing Page", "Form Submission", "Whatsapp Marketing"]
        
        for lead in leads:
            # FILTER: Only save leads with target Lead Sources
            lead_source = lead.get('Lead_Source', '')
            if lead_source is None:
                lead_source = ''
            
            if lead_source not in target_sources:
                print(f"⚠️ Skipping lead {lead.get('First_Name', 'Unknown')} - Lead_Source is '{lead.get('Lead_Source', 'None')}', not in target sources")
                continue
                
            # Get phone number (prefer Mobile over Phone)
            phone = lead.get('Mobile') or lead.get('Phone')
            phone = self.normalize_phone_number(phone)
            
            processed_lead = {
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
                'fetched_at': current_time,
                'message_sent': 'No'  # First run, no messages sent yet
            }
            processed_leads.append(processed_lead)
        
        # Write to CSV (append mode for new leads)
        with open(LEADS_CSV_FILE, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=self.leads_csv_headers)
            
            # Write headers if file doesn't exist
            if not file_exists:
                writer.writeheader()
                
            writer.writerows(processed_leads)
        
        print(f"✅ {len(processed_leads)} leads saved to {LEADS_CSV_FILE}")
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

    def send_aisensy_message(self, phone, user_name, template_params=None):
        """Sends a WhatsApp message via AiSensy API."""
        url = "https://backend.aisensy.com/campaign/t1/api/v2"

        payload = {
            "apiKey": AISENSY_API_KEY,
            "campaignName": CAMPAIGN_NAME,
            "destination": phone,
            "userName": user_name,
            "source": "Zoho CRM Automation",
            "media": {
                "url": WELCOME_IMAGE_URL,
                "filename": IMAGE_FILENAME
            },
            "templateParams": template_params or []
        }

        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, json=payload, headers=headers)
            return response.json()
        except:
            return {"status_code": response.status_code, "text": response.text}

    def send_welcome_messages_to_new_leads(self, new_leads):
        """Sends welcome WhatsApp messages to new leads and updates CSV with message status."""
        if not new_leads:
            print("📱 No new leads to send messages to.")
            return
        
        # Read existing CSV to check for leads that already have messages sent
        existing_leads_with_messages = set()
        if os.path.exists(LEADS_CSV_FILE):
            try:
                df = pd.read_csv(LEADS_CSV_FILE)
                # Get IDs of leads that already have messages sent
                sent_df = df[df.get('message_sent', 'No') == 'Yes']
                existing_leads_with_messages = set(sent_df['id'].astype(str).tolist())
            except Exception as e:
                print(f"⚠️ Error reading message status: {e}")
        
        successful_sends = 0
        failed_sends = 0
        skipped_sends = 0
        no_phone_skips = 0
        
        print(f"📱 Processing {len(new_leads)} leads for messaging...")
        
        for i, lead in enumerate(new_leads, 1):
            lead_id = str(lead.get('id', ''))
            phone = lead.get('phone')
            first_name = lead.get('first_name', 'Friend')
            
            # Skip if message already sent to this lead
            if lead_id in existing_leads_with_messages:
                skipped_sends += 1
                # Only log first few skips to avoid spam
                if skipped_sends <= 3:
                    print(f"⏭️ Skipping {first_name} - message already sent")
                elif skipped_sends == 4:
                    print(f"⏭️ ... and {len(new_leads) - i + 1} more leads already processed (suppressing further skip logs)")
                continue
            
            if not phone:
                no_phone_skips += 1
                # Only log first few no-phone skips
                if no_phone_skips <= 3:
                    print(f"⚠️ Skipping {first_name} - no phone number")
                elif no_phone_skips == 4:
                    print(f"⚠️ ... and more leads without phone numbers (suppressing further logs)")
                continue
            
            print(f"📱 [{i}/{len(new_leads)}] Sending welcome message to {first_name} ({phone})")
            
            # Send message with first name as template parameter
            response = self.send_aisensy_message(
                phone=phone,
                user_name=f"{first_name} {lead.get('last_name', '')}".strip(),
                template_params=[first_name]
            )
            
            # Check for success - AiSensy returns 'success': 'true' as string
            message_sent_status = 'No'
            if (response.get('success') == 'true' or 
                response.get('status') == 'success' or 
                response.get('status_code') == 200):
                successful_sends += 1
                message_sent_status = 'Yes'
                print(f"✅ Message sent successfully to {first_name}")
            else:
                failed_sends += 1
                # Only log first few failures in detail to avoid spam
                if failed_sends <= 5:
                    print(f"❌ Failed to send message to {first_name}: {response}")
                elif failed_sends == 6:
                    print(f"❌ ... and more failures (suppressing detailed error logs)")
                else:
                    print(f"❌ Failed to send message to {first_name}")
            
            # Update the lead record with message status
            lead['message_sent'] = message_sent_status
            
            # Add small delay to avoid rate limiting
            time.sleep(2)
            
            # Progress update for large batches
            if i % 50 == 0:
                print(f"📊 Progress: {i}/{len(new_leads)} leads processed...")
        
        # Update CSV with message status
        self.update_message_status_in_csv(new_leads)
        
        print(f"\n📊 Final Message Summary:")
        print(f"✅ Successfully sent: {successful_sends}")
        print(f"❌ Failed to send: {failed_sends}")
        print(f"⏭️ Skipped (already sent): {skipped_sends}")
        print(f"⚠️ Skipped (no phone): {no_phone_skips}")
        print(f"📱 Total processed: {len(new_leads)}")
        
        # Alert for large skip counts
        if skipped_sends > 100:
            print(f"⚠️ HIGH SKIP COUNT: {skipped_sends} leads already have messages sent")
        if no_phone_skips > 50:
            print(f"⚠️ HIGH NO-PHONE COUNT: {no_phone_skips} leads missing phone numbers")
    
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
            
            # Save only new leads to CSV
            if new_leads:
                processed_new_leads = []
                target_sources = ["Google Landing Page", "Form Submission", "Whatsapp Marketing"]
                
                for lead in new_leads:
                    # FILTER: Only save leads with target Lead Sources
                    lead_source = lead.get('Lead_Source', '')
                    if lead_source is None:
                        lead_source = ''
                    
                    if lead_source not in target_sources:
                        print(f"⚠️ Skipping new lead {lead.get('First_Name', 'Unknown')} - Lead_Source is '{lead.get('Lead_Source', 'None')}', not in target sources")
                        continue
                        
                    phone = lead.get('Mobile') or lead.get('Phone')
                    phone = self.normalize_phone_number(phone)
                    
                    processed_lead = {
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
                        'fetched_at': datetime.now().isoformat(),
                        'message_sent': 'No'  # Will be updated after sending message
                    }
                    processed_new_leads.append(processed_lead)
                
                # Save new leads to CSV
                with open(LEADS_CSV_FILE, 'a', newline='', encoding='utf-8') as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=self.leads_csv_headers)
                    writer.writerows(processed_new_leads)
                
                print(f"✅ {len(processed_new_leads)} new leads saved to CSV")
                
                # Send WhatsApp messages to new leads
                self.send_welcome_messages_to_new_leads(processed_new_leads)
            else:
                print("📱 No new leads found.")
        else:
            # First run - save all leads to CSV
            self.save_leads_to_csv(leads)
            print("📝 First run completed. Next run will check for new leads and send messages.")
        
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
