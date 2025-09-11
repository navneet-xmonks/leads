# 🚀 Erickson Lead Automation - GitHub Actions Deployment

Automated lead processing system that fetches leads from Zoho CRM, filters for test leads, saves to CSV, and sends WhatsApp welcome messages via AiSensy.

## 📋 Features
- ✅ Fetches only leads with Lead_Source = "test" from Zoho CRM
- ✅ Smart token management (only refreshes when needed)
- ✅ Detects new leads and sends WhatsApp messages
- ✅ Runs automatically every 6 hours
- ✅ CSV backup of all processed leads
- ✅ Error handling and detailed logging
- ✅ GitHub Actions automation with artifact storage

## 🛠️ GitHub Actions Setup

### Step 1: Fork/Upload Repository
1. Create a new GitHub repository
2. Upload all files to the repository

### Step 2: Configure Secrets
Go to your GitHub repository → Settings → Secrets and variables → Actions

Add these **Repository Secrets**:

#### Zoho API Credentials:
- `ZOHO_CLIENT_ID`: Your Zoho OAuth Client ID
- `ZOHO_CLIENT_SECRET`: Your Zoho OAuth Client Secret  
- `ZOHO_REFRESH_TOKEN`: Your Zoho OAuth Refresh Token
- `ZOHO_API_DOMAIN`: Your Zoho API domain (e.g., `https://www.zohoapis.com`)

#### AiSensy API Credentials:
- `AISENSY_API_KEY`: Your AiSensy API key for WhatsApp messaging

### Step 3: Get Zoho OAuth Tokens (One-time Setup)

#### Option A: Use Zoho OAuth Playground
1. Go to [Zoho API Console](https://api-console.zoho.com/)
2. Create a new app or use existing
3. Generate OAuth credentials
4. Use the OAuth playground to get refresh token

#### Option B: Manual OAuth Flow
1. Visit this URL (replace CLIENT_ID with yours):
```
https://accounts.zoho.com/oauth/v2/auth?scope=ZohoCRM.modules.ALL&client_id=YOUR_CLIENT_ID&response_type=code&access_type=offline&redirect_uri=https://www.example.com
```

2. Authorize and copy the code from redirect URL
3. Exchange code for tokens:
```bash
curl -X POST https://accounts.zoho.com/oauth/v2/token \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "code=YOUR_CODE" \
  -d "grant_type=authorization_code" \
  -d "redirect_uri=https://www.example.com"
```

### Step 4: Enable GitHub Actions
1. Go to repository → Actions tab
2. Enable GitHub Actions if prompted
3. The workflow will start running automatically

### Step 5: Monitor Execution
- **Manual Run**: Actions tab → "Erickson Lead Automation" → "Run workflow"
- **Scheduled Runs**: Every 30 minutes automatically
- **Logs**: Click on any run to see detailed logs
- **CSV Download**: Each run uploads the CSV as an artifact

## ⚙️ Configuration

### Scheduling
Edit `.github/workflows/lead-automation.yml` to change schedule:
```yaml
schedule:
  - cron: '*/30 * * * *'  # Every 30 minutes
  - cron: '0 */2 * * *'   # Every 2 hours
  - cron: '0 9 * * *'     # Daily at 9 AM
```

### Lead Filtering
The automation only processes leads with `Lead_Source = "test"`. To change this, modify the filtering logic in `lead_automation.py`.

## 📊 Monitoring & Troubleshooting

### Check Run Status
- Green ✅: Successful run
- Red ❌: Failed run (check logs)
- Yellow 🟡: In progress

### Common Issues
1. **"No refresh token found"**: Check ZOHO_REFRESH_TOKEN secret
2. **"403 Forbidden"**: API credentials might be wrong
3. **"No test leads found"**: Check if leads exist in Zoho with Lead_Source = "test"
4. **WhatsApp failures**: Verify AISENSY_API_KEY and campaign setup

### View Logs
1. Go to Actions tab
2. Click on any run
3. Click "lead-automation" job
4. Expand steps to see detailed logs

## 📁 Files Structure
```
├── .github/workflows/
│   └── lead-automation.yml    # GitHub Actions workflow
├── lead_automation.py         # Main automation script
├── requirements.txt           # Python dependencies
└── README.md                 # This file
```

## 🔐 Security
- All sensitive data stored in GitHub Secrets
- Tokens are never logged or exposed
- CSV files are uploaded as artifacts (private to repository)

## 💰 Cost
- **GitHub Actions**: Free (2000 minutes/month on free plan)
- **Estimated Usage**: ~5 minutes/month for this automation
- **Additional Cost**: $0/month 🎉

## 🚀 Next Steps
1. Monitor first few runs to ensure everything works
2. Adjust scheduling as needed
3. Check WhatsApp message delivery
4. Review CSV data for accuracy

---

🎯 **Your automation is now live and will run every 30 minutes automatically!**
