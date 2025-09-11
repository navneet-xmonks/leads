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
        with open(LAST_RUN_FILE, 'w') as f:
            json.dump({'last_run': datetime.now().isoformat()}, f)
    
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
        
    def load_tokens(self):
        """Loads tokens from the JSON file if it exists, or from environment variables."""
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        
        # If no token file exists, try to create from environment variables (for GitHub Actions)
        env_tokens = {}
        if os.getenv('ZOHO_REFRESH_TOKEN'):
            env_tokens = {
                'refresh_token': os.getenv('ZOHO_REFRESH_TOKEN'),
                'api_domain': os.getenv('ZOHO_API_DOMAIN', 'https://www.zohoapis.com')
            }
            # Save to file for persistence during the run
            with open(TOKEN_FILE, 'w') as f:
                json.dump(env_tokens, f, indent=4)
            print("✅ Initialized tokens from environment variables")
            return env_tokens
        
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
        """Uses the refresh token to get a new access token."""
        print("🔄 Refreshing access token...")
        payload = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }

        try:
            response = requests.post(TOKEN_URL, data=payload)
            response.raise_for_status()
            
            new_token_data = response.json()
            if 'refresh_token' not in new_token_data:
                new_token_data['refresh_token'] = refresh_token
            
            # Add timestamp for the new access token
            new_token_data['access_token_timestamp'] = datetime.now().isoformat()
                
            print("✅ Access token refreshed successfully!")
            return new_token_data

        except requests.exceptions.RequestException as e:
            print(f"❌ Error refreshing access token: {e}")
            return None

    def get_valid_token_data(self):
        """Gets valid token data for Zoho API calls - only refresh if needed."""
        stored_tokens = self.load_tokens()
        refresh_token = stored_tokens.get('refresh_token')
        
        if not refresh_token:
            print("❌ No refresh token found. Please run the initial setup first.")
            return None
        
        # Check if we have a valid access token that doesn't need refreshing
        if self.is_access_token_valid(stored_tokens):
            print("🎯 Using existing valid access token")
            return {
                'access_token': stored_tokens.get('access_token'),
                'refresh_token': refresh_token,
                'api_domain': stored_tokens.get('api_domain')
            }
        
        # Access token is expired or missing, refresh it
        print("🔄 Access token needs refreshing...")
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
        """Compare current leads with existing CSV to find new ones."""
        existing_ids = self.get_existing_lead_ids()
        
        new_leads = []
        for lead in current_leads:
            lead_id = str(lead.get('id', ''))
            if lead_id not in existing_ids:
                new_leads.append(lead)
        
        print(f"🆕 Found {len(new_leads)} new leads to process")
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
        
        for lead in new_leads:
            lead_id = str(lead.get('id', ''))
            phone = lead.get('phone')
            first_name = lead.get('first_name', 'Friend')
            
            # Skip if message already sent to this lead
            if lead_id in existing_leads_with_messages:
                print(f"⏭️ Skipping {first_name} - message already sent")
                skipped_sends += 1
                continue
            
            if not phone:
                print(f"⚠️ Skipping {first_name} - no phone number")
                skipped_sends += 1
                continue
            
            print(f"📱 Sending welcome message to {first_name} ({phone})")
            
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
                print(f"❌ Failed to send message to {first_name}: {response}")
            
            # Update the lead record with message status
            lead['message_sent'] = message_sent_status
            
            # Add small delay to avoid rate limiting
            time.sleep(2)
        
        # Update CSV with message status
        self.update_message_status_in_csv(new_leads)
        
        print(f"\n📊 Message Summary:")
        print(f"✅ Successful: {successful_sends}")
        print(f"❌ Failed: {failed_sends}")
        print(f"⏭️ Skipped (already sent): {skipped_sends}")
    
    def update_message_status_in_csv(self, leads_with_status):
        """Update the CSV file with message sent status for the leads."""
        if not os.path.exists(LEADS_CSV_FILE):
            return
        
        try:
            # Read existing CSV
            df = pd.read_csv(LEADS_CSV_FILE)
            
            # Add message_sent column if it doesn't exist
            if 'message_sent' not in df.columns:
                df['message_sent'] = 'No'
            
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
        self.save_last_run_time()
        
        print("\n🎉 Automation process completed!")
        print("=" * 50)

if __name__ == "__main__":
    automation = LeadAutomation()
    automation.run_automation()
