from socket import *
import socket as sock
import requests as req
import threading
import time
import os

localpath = ''
serverPort = 10002

commands = ['get', 'getcanonicals', 'getaliases', 'getlist', 'getinverse',
            'setip', 'update', 'setalias',
            'rm', 'rminverse', 'rmalias',
            'syntax']

class debugclient(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.count = 0

    def run(self):
        while 1:
            print("Commands: ", commands)
            print("Enter your message to MDNS:")
            msg = input()
            clientSocket = socket(AF_INET, SOCK_DGRAM)
            global myIP
            global serverPort
            clientSocket.sendto(msg.encode(), (myIP, serverPort))
            response = clientSocket.recv(2048).decode()
            print(response)
            clientSocket.close()



logs = []
myIP = ''

def main():
    global localpath
    localpath = os.path.dirname(os.path.realpath(__file__)).replace('\\', '//') + '//'
    global myIP
    myIP = req.get('https://api.ipify.org').text
    debugClient = debugclient()
    debugClient.start()

main()
