import SimpleServer as SS
import SimpleClient as SC
import OnlyServer as OS
import OnlyClient as OC
import InterfaceForm as IF
import threading
import time


class serverThread(threading.Thread):
    ready = False
    def __init__(self, userParam):
        threading.Thread.__init__(self)
        self.userParam = userParam

    def run(self):
        if self.userParam.mode == 'all':
            SS.main(self, self.userParam)
        else:
            OS.main(self, self.userParam)



class clientThread(threading.Thread):
    def __init__(self, userParam):
        threading.Thread.__init__(self)
        self.userParam = userParam

    def run(self):
        if self.userParam.mode == 'all':
            SC.main(self.userParam)
        else:
            OC.main(self.userParam)



def user(userParam):

    if userParam.mode != 'all':
        userParam.userID += ' [only '+ userParam.mode+']'
    userParam.userID += ' - Port: {} -'.format(userParam.myServerPort)

    if userParam.userID not in IF.activeForms:
        IF.activeForms.append(userParam.userID)
    else: return

    if userParam.mode == 'all':
        createClientServer(userParam)
    elif userParam.mode == 'server':
        createServer(userParam)
    elif userParam.mode == 'client':
        createClient(userParam)

    print("{} is ready!".format(userParam.userID))


def createClient(userParam):
    client = clientThread(userParam)
    client.start()

def createServer(userParam):
    server = serverThread(userParam)
    server.start()

def createClientServer(userParam):
    server = serverThread(userParam)
    client = clientThread(userParam)
    server.start()
    while not server.ready:
        time.sleep(0.1)
    client.start()

if __name__ == '__main__':
    main()