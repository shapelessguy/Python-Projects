from requests import get
from tkinter import *
from socket import *
import socket as sock
import tkinter as tk
import threading
import time


MDNS_IP = '151.53.126.43'
MDNS_Port = 10002

HEIGHT = 600
WIDTH = 600

activeForms = []
def rmFromActive(ID):
    for index in range(0, len(activeForms)):
        if activeForms[index] == ID:
            activeForms.pop(index)
            break

def defaultParameters(work_on):
    defaultIP = ''  # should be the user's IP who's gonna be contacted / in debug mode arbitrary
    defaultPort = 10000  # port from which my server will listen
    defaultPortServer = 10000  # user server's port
    defaultMaskIP = ''  # only in debug mode: contacted user will see this IP instead of the real one
    defaultProtocol = 'TCP'  # protocol (can be TCP or UDP)

    if work_on == 'forReal':
        defaultIP = ''
        defaultPort = 10000
        defaultPortServer = 0
        defaultMaskIP = ''
        defaultProtocol = 'TCP'

    if work_on == 'forReal_chatroom':
        defaultIP = 'claudio'
        defaultPort = 10000
        defaultPortServer = 9999
        defaultMaskIP = ''
        defaultProtocol = 'TCP'

    elif work_on == 'debug_UDP':
        defaultIP = 'Anyone'
        defaultPort = 10001
        defaultPortServer = 10000
        defaultMaskIP = 'Claudio'
        defaultProtocol = 'UDP'

    elif work_on == 'debug':
        defaultIP = 'Anyone'
        defaultPort = 10001
        defaultPortServer = 10000
        defaultMaskIP = 'Claudio'
        defaultProtocol = 'TCP'

    elif work_on == 'only_debug':
        defaultIP = 'Only'
        defaultPort = 10000
        defaultPortServer = 10000
        defaultMaskIP = 'Claudio'
        defaultProtocol = 'TCP'

    return defaultIP, defaultPort, defaultPortServer, defaultMaskIP, defaultProtocol

cache = []
class Window():

    work_on = 'debug'
    defaultIP, defaultPort, defaultPortServer, defaultMaskIP, defaultProtocol = defaultParameters(work_on)

    def __init__(self):
        global ip_error
        ip_error = False

        self.myIP = get('https://api.ipify.org').text
        self.win = tk.Tk()
        self.win.title("INTERFACE")
        self.win.geometry(str(WIDTH)+'x'+str(HEIGHT))
        self.win.resizable(False, False)
        self.win.configure(background = "black")
        self.win.grid_columnconfigure(2, weight = 1)

        pres_font = ("Helvetica", 30)
        other_font = ("Helvetica", 15, "bold")
        self.presentation = tk.Label(self.win, text = "Welcome to my first chat app!", fg = 'White', background = 'black', font = pres_font)
        self.presentation.grid(row=0, padx = 20, pady = 20, column=0, sticky = "WE",columnspan = 2)

        self.enter = tk.Label(self.win, text = "Enter the user name or user IP to initialize a chat", fg = 'White', background = 'black', font = other_font)
        self.enter.grid(row=1, pady = 8, column=0, sticky = "WE",columnspan = 2)

        self.ip_entry = tk.Entry(self.win, text = 'ip', font = other_font, justify='center')
        self.ip_entry.grid(row=2, padx = 120, pady = 8, column=0, sticky = "WE", columnspan = 2)
        self.ip_entry.insert(0,self.defaultIP)

        self.space = tk.Label(self.win, fg = 'White', background = 'black')
        self.space.grid(row=3, pady = 7, column=0)

        self.enterPort = tk.Label(self.win, text = "Local Port", fg = 'White', background = 'black', font = other_font)
        self.enterPort.grid(row=4, pady = 15, column=0)
        self.enterRecipPort = tk.Label(self.win, text = "Foreign Port", fg = 'White', background = 'black', font = other_font)
        self.enterRecipPort.grid(row=4, pady = 15, column=1)

        self.port_entry = tk.Entry(self.win, text = 'port', justify='center', font = other_font)
        self.port_entry.grid(row=5, padx = 15,pady = 5, column=0, sticky = "WE")
        self.port_entry.insert(0,self.defaultPort)
        self.portServer_entry = tk.Entry(self.win, text = 'portServer', justify='center', font = other_font)
        self.portServer_entry.grid(row=5, padx = 15,pady = 5, column=1, sticky = "WE")
        self.portServer_entry.insert(0,self.defaultPortServer)


        self.enterMaskIP = tk.Label(self.win, text = "Masked IP (DEBUG)", fg = 'White', background = 'black', font = other_font)
        self.enterMaskIP.grid(row=6, pady = 10, column=0)
        self.enterProtocol = tk.Label(self.win, text = "Protocol", fg = 'White', background = 'black', font = other_font)
        self.enterProtocol.grid(row=6, pady = 10, column=1)

        self.maskIP_entry = tk.Entry(self.win, text = 'maskIP', justify='center', font = other_font)
        self.maskIP_entry.grid(row=7, padx = 15,pady = 0, column=0, sticky = "WE")
        self.maskIP_entry.insert(0,self.defaultMaskIP)
        self.protocol_entry = tk.Entry(self.win, text = 'protocol', justify='center', font = other_font)
        self.protocol_entry.grid(row=7, padx = 15,pady = 0, column=1, sticky = "WE")
        self.protocol_entry.insert(0,self.defaultProtocol)

        self.serverMode = IntVar()
        self.onlyServer = Checkbutton(self.win, text = 'Only server', variable = self.serverMode, fg = 'red', background = 'black', font = other_font)
        self.onlyServer.grid(row=8, pady = 25, column=0)
        self.clientMode = IntVar()
        self.onlyClient = Checkbutton(self.win, text = 'Only client', variable = self.clientMode, fg = 'red', background = 'black', font = other_font)
        self.onlyClient.grid(row=8, pady = 25, column=1)

        self.invert = tk.Button(self.win, text="<->", command = self.Invert)
        self.invert.grid(row=9, padx = 250, pady = 12, column=0, sticky = "WE", columnspan = 2)

        self.button = tk.Button(self.win, text="Try to connect", command = self.tryConnect, font = other_font)
        self.button.grid(row=10, padx = 150, pady = 15, column=0, sticky = "WE", columnspan = 2)


        self.winAfter()
        self.win.mainloop()

    def Invert(self):
        if len(self.maskIP_entry.get())== 0:
            return

        temp = self.ip_entry.get()
        self.ip_entry.delete(0,'end')
        self.ip_entry.insert(0, self.maskIP_entry.get())
        self.maskIP_entry.delete(0,'end')
        self.maskIP_entry.insert(0, temp)

        temp = self.portServer_entry.get()
        self.portServer_entry.delete(0,'end')
        self.portServer_entry.insert(0, self.port_entry.get())
        self.port_entry.delete(0,'end')
        self.port_entry.insert(0, temp)

        if self.serverMode.get() == 1 and self.clientMode.get() == 1:
            if self.clientMode.get() == 1:
                self.serverMode.set(1)
                self.clientMode.set(0)
            else:
                self.serverMode.set(0)
                self.clientMode.set(1)


    def tryConnect(self):
        global ip_error
        ip_error = False
        maskIP = self.maskIP_entry.get().title()
        myIP = checkIP(self.myIP)
        if myIP == 'error': return          #check my IP
        userID = 'User ' + myIP

        type = self.protocol_entry.get().upper()
        if type != 'TCP' and type != 'UDP': return      #check on type

        listeningPort_1 = int(self.port_entry.get())
        listeningPort_2 = int(self.portServer_entry.get())
        #if not checkPortUse(listeningPort_2): return        #check on port use

        if checkIP(self.ip_entry.get()) != 'error':
            destination = checkIP(self.ip_entry.get())          #destination is an IP
        else: destination = self.ip_entry.get().title()         #destination is a name

        LocalMode = len(self.maskIP_entry.get()) != 0



        userParam = userParameters(userID=userID, myname = maskIP, recipientname = destination, type=type,
                                   myServerPort=listeningPort_1, recipientPort=listeningPort_2, mode = self.mode,
                                   destination=destination, maskIP=maskIP, myIP = myIP, localMode=LocalMode)



        global cache
        if LocalMode:
            userParam.destination = myIP
            userParam.userID = 'User ' + maskIP
            cache.append(userParam)
        else:
            isIP = checkIP(destination) == 'error'      #True if destinatin is an IP, False otherwise
            global MDNS_IP
            global MDNS_Port
            myDNS = mdns(MDNS_IP, MDNS_Port, userParam, isIP = isIP)
            myDNS.start()


        return

    def winAfter(self):
        global ip_error
        if ip_error: self.ip_entry.configure(background = 'red')
        else: self.ip_entry.configure(background = 'white')

        if self.serverMode.get() == 1 and self.clientMode.get() == 1:
            if self.mode == 'server':
                self.serverMode.set(0)
                self.clientMode.set(1)
            else:
                self.serverMode.set(1)
                self.clientMode.set(0)

        if self.serverMode.get() == 1:
            self.mode = 'server'
            self.setBackground('white', 'gray')
        elif self.clientMode.get() == 1:
            self.setBackground('gray', 'white')
            self.mode = 'client'
        else:
            self.setBackground('white', 'white')
            self.mode = 'all'

        self.win.after(100, self.winAfter)

    def update(self, logs):
        return

    def setBackground(self, mine, his):
        if str(self.port_entry["background"]) != mine:
            self.port_entry.configure(background=mine)
        if str(self.portServer_entry["background"]) != his:
            self.portServer_entry.configure(background=his)

class userParameters:
    def __init__(self, userID, recipientname, myname, type, myServerPort, recipientPort, destination, maskIP, myIP, localMode, mode):
        self.userID = userID                  # univoque id for each client
        self.myname = myname                  # user name (if found into dns server)
        self.recipientname = recipientname    # recipient name (if found into the dns server)
        self.type = type                      # transport protocol
        self.myServerPort = myServerPort      # user server port
        self.myIP = myIP                      # user IP address
        self.recipientPort = recipientPort    # foreign server port
        self.destination = destination        # foreign IP address
        self.maskIP = maskIP                  # masked IP (debug mode)
        self.mode = mode                      # modality: all / server / client
        self.localMode = localMode            # debug mode


def checkIP(IP):
    units = IP.split('.')
    if len(units)!= 4:
        return 'error'
    newIP = ''
    try:
        for unit in units:
            int_unit = int(unit)
            if(int_unit>255 or int_unit<0): return 'error'
            newIP += str(int_unit)+'.'
    except: return 'error'
    return newIP[:-1]

def checkPortUse(port):
    with sock.socket(AF_INET, SOCK_STREAM) as s:
        try: s.bind(('', port))
        except: return False
        return True

class mdns(threading.Thread):
    def __init__(self, dnsIP, dnsPort, userParam, isIP):
        threading.Thread.__init__(self)
        self.dnsIP = dnsIP
        self.dnsPort  = dnsPort
        self.userParam = userParam
        self.isIP = isIP

    def run(self):
        global ip_error
        try:
            result = self.query(com='getinverse', name=self.userParam.myIP)
            if result != None:
                self.userParam.myname = result.title()
                self.userParam.userID = self.userParam.myname + ' (' + self.userParam.myIP + ')'
        except: None

        if self.isIP:
            try:
                result = self.query(com = 'get', name = self.userParam.destination)
                if result != None:
                    ip_error = False
                    self.userParam.destination = result
                    self.userParam.recipientname = self.userParam.recipientname.title() + ' ('+self.userParam.destination+')'
            except:
                ip_error = True
                return
        else:
            try:
                result = self.query(com = 'getinverse', name = self.userParam.destination)
                if result != None:
                    ip_error = False
                    self.userParam.recipientname = result.title() +  ' ('+self.userParam.destination+')'
            except:
                return
        global cache
        cache.append(self.userParam)

    def query(self, com, name):
        global ip_error
        msg = com + ' ' + name
        clientSocket = socket(AF_INET, SOCK_DGRAM)
        clientSocket.settimeout(2)
        clientSocket.sendto(msg.encode(), (self.dnsIP, self.dnsPort))
        response = clientSocket.recv(2048).decode()
        lines = response.split('\n')
        ip_error = True
        if len(lines) == 2:
            if not lines[1].__contains__(' not found'):
                clientSocket.close()
                return lines[1]
            else:
                clientSocket.close()
                return None
