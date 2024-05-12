import announcements
import datetime

last_announcement, id_last_announcement = announcements.get_last_announcement()

for i in range(6000):
    last_announcement, id_last_announcement = announcements.update(datetime.datetime.now() + datetime.timedelta(minutes=(i)), last_announcement, id_last_announcement)

# announcements.set_announcement(datetime.datetime.now())