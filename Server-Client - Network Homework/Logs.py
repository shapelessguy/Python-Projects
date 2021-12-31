import time

class Log():
    def __init__(self, msg, port, received, ID, maskedSend, maskedRecip):
        self.msg = msg
        self.port = port
        self.received = received
        self.ID = ID
        self.maskedSend = maskedSend
        self.maskedRecip = maskedRecip
        self.time = time.time()
        self.year, self.month, self.day, self.hour, self.min, self.sec = map(int, time.strftime("%Y %m %d %H %M %S").split())

    def showList(self):
        hour, min, sec = (self.hour, self.min, self.sec)
        if(hour<10): hour = '0'+ str(self.hour)
        if(min<10): min = '0'+ str(self.min)
        if(sec<10): sec = '0'+ str(self.sec)
        if self.received:
            return '[{}:{}:{}] \u2190  '.format(hour, min, sec) + self.msg
        else:
            return '[{}:{}:{}] \u2192  '.format(hour, min, sec) + self.msg


if __name__ == '__main__':
    main()