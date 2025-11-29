import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv
from datetime import datetime
import pytz

load_dotenv()

credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'service-account.json')

try:
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    
    service = build('calendar', 'v3', credentials=credentials)
    
    # Try to access primary calendar (should now be user's calendar)
    print("=== Testing primary calendar access ===")
    try:
        calendar = service.calendars().get(calendarId='primary').execute()
        print(f"Calendar name: {calendar.get('summary', 'primary')}")
        print(f"Calendar ID: {calendar.get('id', 'N/A')}")
        
        # Check events
        now = datetime.now(pytz.timezone('Europe/Moscow')).isoformat()
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            maxResults=10,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        print(f"\nFound {len(events)} upcoming events:")
        for event in events:
            summary = event.get('summary', 'No title')
            event_id = event.get('id', 'N/A')
            start = event.get('start', {}).get('dateTime', event.get('start', {}).get('date', 'N/A'))
            print(f"  - {summary[:50]} ({event_id[:20]}...)")
            print(f"    Start: {start}")
        
        # Check if our event is there
        print("\n=== Checking for event 6mhk3d6il0bel3d1bocvivdqa8 ===")
        try:
            event = service.events().get(calendarId='primary', eventId='6mhk3d6il0bel3d1bocvivdqa8').execute()
            print(f"Event found in primary calendar!")
            print(f"Summary: {event.get('summary', 'No title')}")
            print(f"Start: {event.get('start', {}).get('dateTime', 'N/A')}")
        except Exception as e:
            print(f"Event not found in primary calendar: {e}")
            print("(This is OK if it was created before sharing was set up)")
    
    except Exception as e:
        print(f"Error accessing primary calendar: {e}")
        import traceback
        traceback.print_exc()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

