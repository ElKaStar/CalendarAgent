import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()

credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'service-account.json')
calendar_id = os.getenv('GOOGLE_CALENDAR_ID', 'primary')

print(f"Testing calendar: {calendar_id}")

try:
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    
    service = build('calendar', 'v3', credentials=credentials)
    
    # Try to access user's calendar
    print(f"\n=== Accessing calendar: {calendar_id} ===")
    try:
        calendar = service.calendars().get(calendarId=calendar_id).execute()
        print(f"Calendar name: {calendar.get('summary', calendar_id)}")
        print(f"Calendar ID: {calendar.get('id', 'N/A')}")
        
        # Check events
        now = datetime.now(pytz.timezone('Europe/Moscow')).isoformat()
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=now,
            maxResults=5,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        print(f"\nFound {len(events)} upcoming events:")
        for event in events:
            summary = event.get('summary', 'No title')
            event_id = event.get('id', 'N/A')
            start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', 'N/A'))
            # Use ASCII encoding to avoid Unicode errors
            summary_ascii = summary.encode('ascii', 'ignore').decode()
            print(f"  - {summary_ascii[:50]}")
            print(f"    ID: {event_id[:30]}...")
            print(f"    Start: {start}")
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

