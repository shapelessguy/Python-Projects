import datetime
import multiprocessing
import os.path
import json
import time
from dotenv import dotenv_values
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

main_folder = os.path.dirname(__file__)

class Calendar:

    def __init__(self) -> None:
        self.connect()
        self.get_calendars()

    def connect(self):
        """Shows basic usage of the Google Calendar API.
        Prints the start and name of the next 10 events on the user's calendar.
        """
        google_client = json.loads(dotenv_values(os.path.join(main_folder, '.env'))['GOOGLE_CRED'])
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        creds = Credentials.from_authorized_user_info(google_client, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                raise Exception
        self.creds = creds
        self.service = build("calendar", "v3", credentials=self.creds)

    def get_calendars(self):
        self.calendars = {}
        page_token = None
        while True:
            calendar_list = self.service.calendarList().list(pageToken=page_token).execute()
            for calendar_list_entry in calendar_list['items']:
                self.calendars[calendar_list_entry['summary']] = calendar_list_entry
            page_token = calendar_list.get('nextPageToken')
            if not page_token:
                break

    def getFirstNItems(self, n: int, calendars=()):
        try:
            now = datetime.datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
            print(f"Getting the upcoming {n} events")
            events_result = []
            for cal in calendars:
                events_result += [
                    self.service.events().list(
                        calendarId=self.calendars[cal]['id'],
                        timeMin=now,
                        maxResults=n,
                        singleEvents=True,
                        orderBy="startTime",
                    ).execute()
                ]
            events = [el for ev in events_result for el in ev.get("items", [])][:n]
            if not events:
                print("No upcoming events found.")
                return  
            
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                print(start, event["summary"])
        except HttpError as error:
            print(f"An error occurred: {error}")
    
    def insertEvent(self):
        event = {
            'summary': 'Google test',
            'location': 'casa',
            'description': 'A chance to hear more about Google\'s developer products.',
            'start': {
                'dateTime': '2024-04-07T09:00:00',
                'timeZone': 'Europe/Rome',
            },
            'end': {
                'dateTime': '2024-04-07T17:00:00',
                'timeZone': 'Europe/Rome',
            },
            'recurrence': [
                'RRULE:FREQ=DAILY;COUNT=2'
            ],
            'reminders': {
                'useDefault': False,
                'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
                ],
            },
        }

        event = self.service.events().insert(calendarId='primary', body=event).execute()
        print('Event created: %s' % (event.get('htmlLink')))







if __name__ == "__main__":
    raise
    calendar = Calendar()
    calendar.getFirstNItems(10, calendars=['Hobby&Sport', 'Birthday'])
    calendar.insertEvent()

b = {'kind': 'calendar#event', 
     'etag': '"3354900265976000"', 
     'id': '14cjha7761ol5k32mket54jqoi_20240408T163000Z', 
     'status': 'confirmed', 
     'htmlLink': 'https://www.google.com/calendar/event?eid=MTRjamhhNzc2MW9sNWszMm1rZXQ1NGpxb2lfMjAyNDA0MDhUMTYzMDAwWiBzaGFwZWxlc3NndXlAbQ', 
     'created': '2023-02-26T22:22:12.000Z', 
     'updated': '2023-02-26T22:22:12.988Z', 
     'summary': 'Gym', 
     'creator': {'email': 'shapelessguy@gmail.com', 'self': True}, 
     'organizer': {'email': 'shapelessguy@gmail.com', 'self': True}, 
     'start': {'dateTime': '2024-04-08T18:30:00+02:00', 'timeZone': 'Europe/Rome'}, 
     'end': {'dateTime': '2024-04-08T20:30:00+02:00', 'timeZone': 'Europe/Rome'}, 
     'recurringEventId': '14cjha7761ol5k32mket54jqoi', 
     'originalStartTime': {'dateTime': '2024-04-08T18:30:00+02:00', 'timeZone': 'Europe/Rome'}, 
     'iCalUID': '14cjha7761ol5k32mket54jqoi@google.com', 
     'sequence': 0, 
     'reminders': {'useDefault': True}, 
     'eventType': 'default'
     }
