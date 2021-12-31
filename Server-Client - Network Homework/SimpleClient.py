from requests import get
from socket import *
import threading
import time
import SimpleClientForm
import InterfaceForm as IF
import tkinter as tk
import Logs


class clientForm(threading.Thread):
    def __init__(self, userParam):
        self.Alive = True
        self.mainAlive = True
        self.userParam = userParam
        self.cache = []
        threading.Thread.__init__(self)

    def run(self):
        SimpleClientForm.Window(self.userParam.userID, self.userParam.recipientname, self.userParam.maskIP,
                                           self.userParam.destination, self.cache, self.userParam.mode)
        self.Alive = False
        self.close()

    def close(self):
        IF.rmFromActive(self.userParam.userID)
        while self.mainAlive:
            time.sleep(0.2)



logs = []
def main(userParam):
    Form = clientForm(userParam)
    Form.start()

    Activity(Form, userParam)
    Form.mainAlive = False
    IF.rmFromActive(userParam.userID)
    print("Client ({}) is closed!".format(userParam.userID))

def createSocket(type):
    if type == 'TCP':
        clientSocket = socket(AF_INET, SOCK_STREAM)
    elif type == 'UDP':
        clientSocket = socket(AF_INET, SOCK_DGRAM)
    return clientSocket

def tryConnect(clientSocket, userParam):
    try:
        if userParam.type == 'TCP':
            clientSocket.settimeout(3)
            clientSocket.connect((userParam.destination, userParam.recipientPort))
            clientSocket.settimeout(None)
        else: return True
    except Exception as e:
        print(e);
        if e.args[0] == 10056: return True
        return False
    return True

def sendMsg(clientSocket, msg, type, destination, serverPort):
    if type == 'TCP':
        clientSocket.send(msg.encode())
    elif type == 'UDP':
        clientSocket.sendto(msg.encode(), (destination, serverPort))

def Activity(Form, userParam):
    try:
        sleepingTime = 0.05
        clientSocket = createSocket(userParam.type)
        while Form.Alive:                               # first attempt to connect
            if tryConnect(clientSocket, userParam): break
            else: time.sleep(3)
        while Form.Alive:
            time.sleep(sleepingTime)
            try:
                if len(Form.cache)>0:
                    for index in range(0, len(Form.cache)):
                        if index >= len(Form.cache): break
                        time.sleep(sleepingTime)
                        msg = Form.cache[index]
                        sendMsg(clientSocket, msg, userParam.type, userParam.destination, userParam.recipientPort)
                        if userParam.localMode: maskSend = userParam.maskIP
                        else: maskSend = userParam.myIP
                        logs.append(Logs.Log(msg=msg, port=userParam.recipientPort, received=False, ID=userParam.userID,
                                                 maskedSend=maskSend, maskedRecip=userParam.destination))
                        Form.cache.pop(0)
            except Exception as ex:
                print(ex)
                clientSocket = createSocket(userParam.type)     # if connection goes down
                tryConnect(clientSocket, userParam)
                print('Reconnecting')
                time.sleep(3)
        clientSocket.close()
    except Exception as e:
        print("Exception: {} - Client is closed".format(e))


if __name__ == '__main__':
    main()