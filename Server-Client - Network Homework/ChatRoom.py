import threading
import time
from socket import *

serverPort = 9999
MDNS_IP = '151.53.126.43'
MDNS_Port = 10002
cache = []
users = []
logs = []


class sendThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        sleepingTime = 0.05
        global cache
        while 1:
            try:
                time.sleep(sleepingTime)
                if len(cache) > 0:
                    for index in range(0, len(cache)):
                        if index >= len(cache): break
                        for user in users:
                            if cache[index].user == None or cache[index].user.IP != user.IP or cache[index].user.Port != user.Port:
                                time.sleep(sleepingTime)
                                msg = cache[index].msg
                                user.socket.send(msg.encode())
                        cache.pop(index)
            except: None

class connectionThread(threading.Thread):
    def __init__(self, port):
        threading.Thread.__init__(self)
        self.port = port

    def run(self):
        try:
            serverSocket = socket(AF_INET, SOCK_STREAM)
            serverSocket.bind(('', self.port))
            while 1:
                serverSocket.listen(1)
                connectSocket, clientAddress = serverSocket.accept()
                found = False
                for user in users:
                    if clientAddress[0] == user.IP and clientAddress[1] == user.Port: found = True
                if not found:
                    users.append(User(connectSocket, clientAddress))
                    receiver = receiveThread(users[-1])
                    receiver.start()
        except: print('Error on port {}'.format(self.port))

class receiveThread(threading.Thread):
    def __init__(self, user):
        threading.Thread.__init__(self)
        self.user = user
        global users
        n_connected = len(users)
        user.socket.send('Dear {}, welcome to the ChatRoom! there are {} users currently connected'.format(user.name, n_connected).encode())
        if user.IP != user.name: complete_name = user.name + ' ('+ user.IP + ')'
        else: complete_name = 'User '+ user.IP
        message = '{} has joined the chat'.format(complete_name)
        cache.append(Log(msg = message, user = None))

    def run(self):
        try:
            while 1:
                message = self.user.socket.recv(2048).decode()
                if message:
                    message = self.user.name + " > " + message
                    logs.append(Log(msg=message, user = self.user))
                    cache.append(logs[-1])
                else: break
        except: None
        global users
        for index in range(len(users)):
            if self.user.IP == users[index].IP and self.user.Port == users[index].Port:
                users.pop(index)
                break
        if self.user.IP != self.user.name: complete_name = self.user.name + ' ('+ self.user.IP + ')'
        else: complete_name = 'User '+ self.user.IP
        message = '{} has left the chat'.format(complete_name)
        cache.append(Log(msg = message, user = None))

def main():
    global serverPort
    connectionManager = connectionThread(serverPort)
    connectionManager.start()
    time.sleep(0.01)
    if not connectionManager.is_alive(): return
    print('Server ready!')
    sender = sendThread()
    sender.start()
    print('Also ready to send!')

class User():
    def __init__(self, clientSocket, clientAddress):
        self.name = clientAddress[0]
        self.IP = clientAddress[0]
        self.Port = clientAddress[1]
        self.connectionTime = time.time()
        self.socket = clientSocket
        try:
            result = self.query(com='getinverse', name=self.name)
            if result != None: self.name = result.title()
        except: None

    def query(self, com, name):
        msg = com + ' ' + name
        clientSocket = socket(AF_INET, SOCK_DGRAM)
        clientSocket.settimeout(2)
        try:
            global MDNS_IP
            global MDNS_Port
            if MDNS_IP == '' or MDNS_Port == '': return None
            clientSocket.sendto(msg.encode(), (MDNS_IP, MDNS_Port))
        except: return None
        response = clientSocket.recv(2048).decode()
        lines = response.split('\n')
        if len(lines) == 2:
            if not lines[1].__contains__(' not found'):
                clientSocket.close()
                return lines[1]
            else:
                clientSocket.close()
                return None


class Log():
    def __init__(self, msg, user):
        self.msg = msg
        self.user = user
        self.time = time.time()
        print(msg)


if __name__ == '__main__':
    main()