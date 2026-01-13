import time
import schedule

from lead_automation import LeadAutomation


def run_once():
    automation = LeadAutomation()
    automation.run_automation()


if __name__ == "__main__":
    # Run once on startup, then every 2 minutes.
    run_once()
    schedule.every(2).minutes.do(run_once)

    while True:
        schedule.run_pending()
        time.sleep(30)
