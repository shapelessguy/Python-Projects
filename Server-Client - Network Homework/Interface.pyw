import InterfaceForm as IF
import Supervisor as SV
import tkinter as tk
import threading
import time

class interfaceThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        IF.Window()


class userThread(threading.Thread):
    def __init__(self, userParam):
        threading.Thread.__init__(self)
        self.userParam = userParam

    def run(self):
        SV.user(self.userParam)



def main():
    interface = interfaceThread()
    interface.start()

    while interface.is_alive():
        time.sleep(0.2)
        while len(IF.cache)>0:
            user = userThread(IF.cache[0])
            IF.cache.clear()
            user.start()
            time.sleep(0.2)

    while len(IF.activeForms)>0:
        time.sleep(1)


if __name__ == '__main__':
    main()