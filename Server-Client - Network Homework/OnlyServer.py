from tkinter import messagebox
from requests import get
from tkinter import *
from socket import *
import InterfaceForm as IF
import SimpleClientForm
import socket as sock
import tkinter as tk
import threading
import time
import Logs
import sys

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
        IF.rmFromActive(self.userParam.userID.replace('[only server]', '[only client]'))
        while self.mainAlive:
            time.sleep(0.1)

def sendMsg(clientSocket, msg, type, destination, serverPort):
    if type == 'TCP':
        clientSocket.send(msg.encode())
    elif type == 'UDP':
        clientSocket.sendto(msg.encode(), (destination, serverPort))

class send(threading.Thread):
    def __init__(self, checkthread, userParam, Form):
        self.mustClose = False
        self.userParam = userParam
        self.checkthread = checkthread
        self.Form = Form
        threading.Thread.__init__(self)

    def run(self):
        sleepingTime = 0.05
        while not self.mustClose:
            try:
                time.sleep(sleepingTime)
                try:
                    if len(self.Form.cache) > 0:
                        for index in range(0, len(self.Form.cache)):
                            if index >= len(self.Form.cache): break
                            time.sleep(sleepingTime)
                            msg = self.Form.cache[index]
                            sendMsg(self.checkthread.connectSocket, msg, self.userParam.type, self.userParam.destination,
                                    self.userParam.recipientPort)
                            if self.userParam.localMode: maskSend = self.userParam.maskIP
                            else: maskSend = self.userParam.myIP
                            logs.append(Logs.Log(msg=msg, port=self.userParam.recipientPort, received=False, ID=self.userParam.userID,
                                     maskedSend=maskSend, maskedRecip=self.userParam.destination))
                            self.Form.cache.pop(index)
                except: None
            except: None

class check(threading.Thread):
    def __init__(self, ID, serverSocket):
        self.ID = ID
        self.serverSocket = serverSocket
        self.connectSocket = None
        self.mustClose = False
        threading.Thread.__init__(self)

    def run(self):
        while self.ID in IF.activeForms:
            time.sleep(0.1)
        self.close()

    def close(self):
        time.sleep(0.1)
        try:
            if self.serverSocket != None:
                self.serverSocket.close()
                if self.connectSocket != None: self.connectSocket.close()
                self.mustClose = True
        except: None


def main(thread, userParam):
    Form = clientForm(userParam)
    Form.start()

    if userParam.type=='TCP':
        createTCP(thread, userParam, Form)
    elif userParam.type == 'UDP':
        createUDP(thread, userParam, Form)
    IF.rmFromActive(userParam.userID)
    IF.rmFromActive(userParam.userID.replace('[only server]', '[only client]'))
    Form.mainAlive = False
    print("Server ({}) is closed!".format(userParam.userID))


logs = []
def createTCP(thread, userParam, Form):
    try:
        serverSocket = socket(AF_INET, SOCK_STREAM)
        serverSocket.bind(('', userParam.myServerPort))
        checkSocket = check(userParam.userID, serverSocket)
        checkSocket.start()
        sender = send(checkSocket, userParam, Form)
        sender.start()
        while 1:
            serverSocket.listen(1)
            thread.ready = True
            connectSocket, clientAddress = serverSocket.accept()
            checkSocket.connectSocket = connectSocket
            try:
                while not checkSocket.mustClose:
                    sentence = connectSocket.recv(2048).decode()
                    if sentence and not checkSocket.mustClose:
                        manage(msg = sentence, addr = clientAddress, userParam = userParam)
            except: None
            connectSocket.close()
        serverSocket.close
    except: None
    sender.mustClose = True


def createUDP(thread, userParam, Form):
    try:
        serverSocket = socket(AF_INET, SOCK_DGRAM)
        serverSocket.bind(('', userParam.myServerPort))
        thread.ready = True
        checkSocket = check(userParam.userID, serverSocket)
        checkSocket.connectSocket = serverSocket
        checkSocket.start()
        sender = send(checkSocket, userParam, Form)
        sender.start()
        while not checkSocket.mustClose:
            try: message, clientAddress = serverSocket.recvfrom(2048)
            except: return
            sentence = message.decode()
            manage(msg = sentence, addr = clientAddress, userParam = userParam)
        serverSocket.close
    except: None
    sender.mustClose = True


def manage(msg, addr, userParam):
    if userParam.localMode: maskedRecip = userParam.maskIP
    else: maskedRecip = userParam.myIP
    logs.append(Logs.Log(msg=msg, port=addr[1], received=True, ID=userParam.userID,
                         maskedSend=userParam.destination, maskedRecip=maskedRecip))


if __name__ == '__main__':
    main()