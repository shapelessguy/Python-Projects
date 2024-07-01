import os
from encryption import decrypt_message
from exchangelib import Credentials, Account, DELEGATE
from exchangelib import EWSDateTime, EWSTimeZone
from dotenv import dotenv_values
import datetime
import html2text
import time

main_folder = os.path.dirname(__file__)
username = 'dlr\cian_cl'
password = decrypt_message(dotenv_values(os.path.join(main_folder, '.env'))['OUTLOOK_PASS'])
email = 'claudio.ciano@dlr.de'

credentials = Credentials(username, password)
account = Account(email, credentials=credentials, autodiscover=True, access_type=DELEGATE)

# Set the timezone to your local timezone
tz = EWSTimeZone.localzone()

# Define the start and end times for the event fetch
start = EWSDateTime.from_datetime(datetime.datetime.now()).astimezone(tz)
end = EWSDateTime.from_datetime(datetime.datetime.now() + datetime.timedelta(days=30)).astimezone(tz)

events = account.calendar.view(start=start, end=end)

h = html2text.HTML2Text()
h.ignore_links = False

for item in events:
    print("Subject:", item.subject)
    print("Start:", item.start)
    print("End:", item.end)
    print("Location:", item.location)
    print("Organizer:", item.organizer)
    print("Is All Day:", item.is_all_day)
    print("Importance:", item.importance)
    print("Categories:", item.categories)
    print('Body:', h.handle(item.body))
    print("Recurrence:", item.recurrence)
    print("Attendees:", [(attendee.mailbox.email_address, attendee.response_type) for attendee in item.required_attendees])
    print("Attachments:", [attachment.name for attachment in item.attachments])
    # Add more properties as needed