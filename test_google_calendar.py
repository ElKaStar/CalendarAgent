import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'service-account.json')
calendar_id = os.getenv('GOOGLE_CALENDAR_ID', 'primary')

print(f"Credentials file: {credentials_file}")
print(f"Calendar ID: {calendar_id}")

try:
    # Create credentials
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    
    print(f"Service Account email: {credentials.service_account_email}")
    
    # Create service
    service = build('calendar', 'v3', credentials=credentials)
    
    # Check calendar access
    print("\n=== Checking calendar access ===")
    calendar = service.calendars().get(calendarId=calendar_id).execute()
    print(f"Calendar found: {calendar.get('summary', 'primary')}")
    
    # Try to get events list
    print("\n=== Checking events list ===")
    from datetime import datetime
    import pytz
    
    now = datetime.now(pytz.timezone('Europe/Moscow')).isoformat()
    events_result = service.events().list(
        calendarId=calendar_id,
        timeMin=now,
        maxResults=5,
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    print(f"Found events: {len(events)}")
    
    for event in events:
        print(f"  - {event.get('summary', 'No title')} ({event.get('id', 'N/A')})")
    
    # Check specific event
    print("\n=== Checking event 6mhk3d6il0bel3d1bocvivdqa8 ===")
    try:
        event = service.events().get(calendarId=calendar_id, eventId='6mhk3d6il0bel3d1bocvivdqa8').execute()
        print(f"Event found: {event.get('summary', 'No title')}")
        print(f"Start: {event.get('start', {}).get('dateTime', 'N/A')}")
    except Exception as e:
        print(f"Event not found: {e}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
