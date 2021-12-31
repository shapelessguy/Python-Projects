from tkinter import messagebox
from requests import get
from tkinter import *
from socket import *
import socket as sock
import InterfaceForm as IF
import tkinter as tk
import threading
import time
import Logs
import sys

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
        IF.rmFromActive(self.ID)
        if self.serverSocket != None:
            self.serverSocket.close()
            if self.connectSocket != None: self.connectSocket.close()
            self.mustClose = True


def main(thread, userParam):
    if userParam.type=='TCP':
        createTCP(thread, userParam)
    elif userParam.type == 'UDP':
        createUDP(thread, userParam)
    IF.rmFromActive(userParam.userID)
    print("Server ({}) is closed!".format(userParam.userID))


logs = []
def createTCP(thread, userParam):
    try:
        serverSocket = socket(AF_INET, SOCK_STREAM)
        serverSocket.bind(('', userParam.myServerPort))
        checkSocket = check(userParam.userID, serverSocket)
        checkSocket.start()
        serverSocket.listen(1)
        thread.ready = True
        connectSocket, clientAddress = serverSocket.accept()
        checkSocket.connectSocket = connectSocket
        while not checkSocket.mustClose:
            try:
                sentence = connectSocket.recv(2048).decode()
            except:
                sentence = ''
            if sentence and not checkSocket.mustClose:
                manage(msg = sentence, addr = clientAddress, userParam = userParam)
            elif not checkSocket.mustClose:
                time.sleep(0.5)
                try:
                    serverSocket.listen(1)
                    connectSocket, clientAddress = serverSocket.accept()
                    checkSocket.connectSocket = connectSocket
                except: return

        connectSocket.close()
        serverSocket.close
    except: None


def createUDP(thread, userParam):
    try:
        serverSocket = socket(AF_INET, SOCK_DGRAM)
        serverSocket.bind(('', userParam.myServerPort))
        thread.ready = True
        checkSocket = check(userParam.userID, serverSocket)
        checkSocket.start()
        while not checkSocket.mustClose:
            try: message, clientAddress = serverSocket.recvfrom(2048)
            except: return
            sentence = message.decode()
            manage(msg = sentence, addr = clientAddress, userParam = userParam)
        serverSocket.close
    except: None


def manage(msg, addr, userParam):
    if userParam.localMode: maskedRecip = userParam.maskIP
    else: maskedRecip = userParam.myIP
    logs.append(Logs.Log(msg=msg, port=addr[1], received=True, ID=userParam.userID,
                         maskedSend=userParam.destination, maskedRecip=maskedRecip))


if __name__ == '__main__':
    main()