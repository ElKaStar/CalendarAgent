import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'service-account.json')

print(f"Credentials file: {credentials_file}")

try:
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    
    print(f"Service Account email: {credentials.service_account_email}")
    
    service = build('calendar', 'v3', credentials=credentials)
    
    # Try to access primary calendar
    print("\n=== Trying to access primary calendar ===")
    try:
        calendar = service.calendars().get(calendarId='primary').execute()
        print(f"SUCCESS! Primary calendar: {calendar.get('summary', 'primary')}")
        print(f"Calendar ID: {calendar.get('id', 'N/A')}")
    except Exception as e:
        print(f"ERROR accessing primary calendar: {e}")
        print("\n=== Solution ===")
        print(f"You need to share your primary calendar with Service Account:")
        print(f"1. Open Google Calendar: https://calendar.google.com/")
        print(f"2. Settings -> Settings for my calendars -> [Your calendar]")
        print(f"3. Share with specific people")
        print(f"4. Add: {credentials.service_account_email}")
        print(f"5. Permission: 'Make changes to events'")
        print(f"6. Save")
    
    # Check Service Account calendar
    print(f"\n=== Service Account calendar ===")
    sa_calendar_id = credentials.service_account_email
    try:
        calendar = service.calendars().get(calendarId=sa_calendar_id).execute()
        print(f"Service Account calendar: {calendar.get('summary', sa_calendar_id)}")
        
        # Check events in SA calendar
        from datetime import datetime
        import pytz
        now = datetime.now(pytz.timezone('Europe/Moscow')).isoformat()
        events_result = service.events().list(
            calendarId=sa_calendar_id,
            timeMin=now,
            maxResults=5
        ).execute()
        events = events_result.get('items', [])
        print(f"Events in SA calendar: {len(events)}")
        for event in events:
            summary = event.get('summary', 'No title')
            print(f"  - Event ID: {event.get('id', 'N/A')}")
            print(f"    Summary: {summary.encode('ascii', 'ignore').decode()}")
    except Exception as e:
        print(f"Error: {e}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

