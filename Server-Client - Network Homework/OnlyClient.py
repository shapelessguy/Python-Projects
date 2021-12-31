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
            time.sleep(0.1)

class receive(threading.Thread):
    def __init__(self, clientSocket, userParam):
        self.mustClose = False
        self.userParam = userParam
        self.clientSocket = clientSocket
        threading.Thread.__init__(self)

    def run(self):
        while not self.mustClose:
            try:
                message, address = self.clientSocket.recvfrom(2048)
                if message.decode() != '':
                    if self.userParam.localMode: maskedRecip = self.userParam.maskIP
                    else: maskedRecip = self.userParam.myIP
                    logs.append(Logs.Log(msg=message.decode(), port=address[1], received=True, ID=self.userParam.userID,
                                     maskedSend=self.userParam.destination, maskedRecip=maskedRecip))
            except: None


logs = []
def main(userParam):
    Form = clientForm(userParam)
    Form.start()

    Activity(Form, userParam)
    Form.mainAlive = False
    IF.rmFromActive(userParam.userID)
    print("Client ({}) is closed!".format(userParam.userID))

def createSocket(userParam):
    if userParam.type == 'TCP':
        clientSocket = socket(AF_INET, SOCK_STREAM)
    elif userParam.type == 'UDP':
        clientSocket = socket(AF_INET, SOCK_DGRAM)
    return clientSocket

def tryConnect(clientSocket, userParam):
    try:
        if userParam.type == 'TCP':
            clientSocket.settimeout(3)
            clientSocket.connect((userParam.destination, userParam.recipientPort))
            clientSocket.settimeout(None)
        else:
            return True
    except Exception as e:
        if e.args[0] == 10056: return True
        return False
    return True

def Receive(clientSocket, userParam):
    receiver = receive(clientSocket, userParam)
    receiver.start()
    return receiver

def sendMsg(clientSocket, msg, type, destination, serverPort):
    if type == 'TCP':
        clientSocket.send(msg.encode())
    elif type == 'UDP':
        clientSocket.sendto(msg.encode(), (destination, serverPort))

def Activity(Form, userParam):
    try:
        sleepingTime = 0.05
        clientSocket = createSocket(userParam)
        while Form.Alive:                               # first attempt to connect
            if tryConnect(clientSocket, userParam): break
            else: time.sleep(3)
        receiver = Receive(clientSocket, userParam)
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
                        logs.append(Logs.Log(msg=msg, port=userParam.recipientPort, received=False, ID=Form.userParam.userID,
                                                 maskedSend=maskSend, maskedRecip=userParam.destination))
                        Form.cache.pop(index)
            except Exception as ex:
                receiver.mustClose = True
                clientSocket = createSocket(userParam)     # if connection goes down
                tryConnect(clientSocket, userParam)
                time.sleep(3)
                receiver = Receive(clientSocket, userParam)
                print('Reconnecting')
        clientSocket.close()
    except Exception as e:
        print("Exception: {} - Client is closed".format(e))
    try: receiver.mustClose = True
    except: None


if __name__ == '__main__':
    main()