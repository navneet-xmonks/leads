# GitHub Actions Setup Guide

## Quick Setup Steps

### 1. Upload to GitHub
1. Create a new repository on GitHub
2. Upload all your project files including the `.github/workflows/lead-automation.yml` file

### 2. Add Secrets
Go to: **Repository Settings → Secrets and variables → Actions → New repository secret**

Add these secrets:
- `ZOHO_CLIENT_ID` - Your Zoho OAuth Client ID
- `ZOHO_CLIENT_SECRET` - Your Zoho OAuth Client Secret  
- `ZOHO_REFRESH_TOKEN` - Your Zoho OAuth Refresh Token
- `ZOHO_API_DOMAIN` - Your Zoho API domain (usually `https://www.zohoapis.com`)
- `AISENSY_API_KEY` - Your AiSensy API key

### 3. The Automation Will:
- ✅ Run every 6 hours automatically
- ✅ Run when you push code to main branch
- ✅ Can be triggered manually from Actions tab
- ✅ Save CSV files as downloadable artifacts
- ✅ Show detailed logs for debugging

### 4. Monitor Runs
- Go to **Actions** tab in your repository
- Click on any run to see logs
- Download CSV files from the **Artifacts** section

### 5. Manual Trigger
- Go to **Actions** tab
- Click **"Lead Automation"** workflow
- Click **"Run workflow"** button

## What the Workflow Does

1. **Sets up Python 3.10** environment
2. **Installs dependencies** from requirements.txt
3. **Runs your lead_automation.py** script
4. **Uploads CSV files** as artifacts for download
5. **Shows summary** of processed leads

## Scheduling

Current schedule: **Every 6 hours**

To change the schedule, edit `.github/workflows/lead-automation.yml`:

```yaml
schedule:
  - cron: '0 */6 * * *'  # Every 6 hours
  - cron: '0 */2 * * *'  # Every 2 hours  
  - cron: '0 9 * * *'    # Daily at 9 AM
```

## Cost
- **FREE** - Uses GitHub's free Actions minutes
- **Usage**: ~2-3 minutes per run
- **Monthly**: ~360 minutes (well under 2000 minute limit)

Your automation is now live! 🚀
