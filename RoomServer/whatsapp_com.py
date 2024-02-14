# Importing the Required Library
import pywhatkit

# Defining the Phone Number and Message
phone_number = "+491718253298"
message = "Hey!"

# Sending the WhatsApp Message
pywhatkit.sendwhatmsg_instantly(phone_number, message)

# Displaying a Success Message
print("WhatsApp message sent!")

