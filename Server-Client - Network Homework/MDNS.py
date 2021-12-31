from socket import *
import socket as sock
import requests as req
import threading
import time
import os

localpath = ''
serverPort = 10002
mode = 'server'                        # modes = 'server', 'client', 'debug'
msg = 'setip 95.245.13.165 antonio'

commands = ['get', 'getcanonicals', 'getaliases', 'getlist', 'getinverse',
            'setip', 'update', 'setalias',
            'rm', 'rminverse', 'rmalias',
            'syntax']

quit = False


class saveThread(threading.Thread):
    secToSave = 60    # saving every ..

    def __init__(self):
        threading.Thread.__init__(self)
        self.count = 0
        global localpath
        self.localpath = localpath

    def run(self):
        global quit
        while not quit:
            time.sleep(1)
            self.count += 1
            if self.count > 10000: self.count = 10
            if self.count%self.secToSave == 0:
                self.save()

    def save(self):
        with open(self.localpath + "database.txt", "w") as file:
            for key, value in ip_dict.items():
                file.write(key + '|_^_|' + value + '|_^_|' + 'A\n')
            for (key, value) in alias_dict:
                file.write(key + '|_^_|' + value + '|_^_|' + 'CNAME\n')
        with open(self.localpath + "logs.txt", "a") as file:
            for log in logs:
                file.write(log + '\n')
            logs.clear()

class debugclient(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.count = 0

    def run(self):
        time.sleep(1)
        self.count += 1
        if self.count == 1:
            global msg
            clientSocket = socket(AF_INET, SOCK_DGRAM)
            global myIP
            global serverPort
            print(msg)
            clientSocket.sendto(msg.encode(), (myIP, serverPort))
            response = clientSocket.recv(2048).decode()
            print(response)
            clientSocket.close()




def createFolder():
    try: os.mkdir(localpath)
    except OSError as error:
        if error.strerror != 'Impossibile creare un file, se il file esiste già':
            print(error)

def read():
    createFolder()
    if not os.path.isfile(localpath + "database.txt"):
        file = open(localpath + "database.txt", "w")
        file.close()
    with open(localpath + "database.txt", "r") as file:
        lines = file.readlines()
        for line in lines:
            words = line.replace('\n','').split('|_^_|')
            if len(words) != 3: break
            if words[2] == 'A':
                ip_dict[words[0]] = words[1]
            else:
                alias_dict.append((words[0], words[1]))


ip_dict = {}     # ip : canonical
alias_dict = []  # alias : canonical
logs = []
myIP = ''

def main():
    global localpath
    global quit
    localpath = os.path.dirname(os.path.realpath(__file__)).replace('\\', '//') + '//'
    global mode
    if mode == 'client' or mode == 'debug':
        global myIP
        myIP = req.get('https://api.ipify.org').text
        debugClient = debugclient()
        debugClient.start()

    if mode == 'server' or mode == 'debug':
        read()
        saving = saveThread()
        saving.start()
        listen()

    quit = True


def listen():
    try:
        global serverPort
        serverSocket = socket(AF_INET, SOCK_DGRAM)
        serverSocket.bind(('', serverPort))
        print("MDNS is up")
        jump = False
        while 1:
            try: message, clientAddress = serverSocket.recvfrom(2048)
            except: jump = True
            if not jump:
                packDim = 10
                sentence = message.decode()
                response = manage(sentence, clientAddress)
                if type(response) == list:
                    if len(response) > packDim-2:
                        segments = ['Start transmission from MDNS\n']
                    else:
                        segments = ['']
                    for i in range(len(response)):
                        segments[-1] += response[i] + '\n'
                        if i%packDim == 0 and i>0:
                            segments[-1] = segments[-1][:-1]
                            segments.append('')
                    segments[-1] = segments[-1][:-1]
                    if len(response) > packDim-2: segments[-1] += 'End transmission from MDNS'
                    for segment in segments:
                        print(segment)
                        serverSocket.sendto(segment.encode(), clientAddress)
                else:
                    print(response)
                    serverSocket.sendto(response.encode(), clientAddress)
        serverSocket.close
    except: None
    print("MDNS is down")


def manage(sentence, address):

    lines = sentence.split('\n')
    if len(lines) != 1:
        log = sentence.replace('\n','|n|').replace('\r','|r|')
        logs.append(log + ' ||| from {}|{}'.format(address[0], address[1]) + '|' + getHour())
        return 'Answer from MDSN: \nMessage should contain just one line'
    logs.append(sentence + ' ||| from {}|{}'.format(address[0], address[1]) + '|' + getHour())
    words = sentence.split()
    if len(words)<1: return 'Answer from MDSN: \nMessage should have at least one word'
    command = words[0].lower()
    if command not in commands: return 'Answer from MDSN: \nCommand not found'
    values = []
    for word in words[1:]:
        values.append(word.lower())
    query = 'Answer from MDNS: ' + command + ' ' + ' '.join(values) + '\n'
    if(command == 'get'):
        sentence = get(values)
    elif(command == 'getcanonicals'):
        sentence = getcanonicals(values)
    elif(command == 'getaliases'):
        sentence = getaliases(values)
    elif(command == 'getlist'):
        sentence = getlist(values)
    elif(command == 'getinverse'):
        sentence = getinverse(values)
    elif(command == 'setip'):
        sentence = setip(values)
    elif(command == 'update'):
        sentence = update(values)
    elif(command == 'setalias'):
        sentence = setalias(values)
    elif(command == 'rm'):
        sentence = rm(values)
    elif(command == 'rminverse'):
        sentence = rminverse(values)
    elif(command == 'rmalias'):
        sentence = rmalias(values)
    elif(command == 'syntax'):
        sentence = syntax(values)
    else: return 'Internal error'
    if type(sentence) == list:
        sentence.insert(0, query[:-1] + ' ({} results)'.format(len(sentence)))
        return sentence
    else:
        return query + sentence

def get(values):
    '''Get the IP address associated with a canonical name'''
    if len(values) != 1: return 'get-command accepts only one argument'
    for ip, canonical in ip_dict.items():
        if canonical == values[0]:
            return ip
    return 'IP not found'

def getcanonicals(values):
    '''Get the canonical names associated with an alias name, given the alias name'''
    if len(values) != 1: return 'getcanonicals-command accepts only one argument'
    canonicals = []
    for (alias, canonical) in alias_dict:
        if alias == values[0]:
            canonicals.append(canonical)
    if len(canonicals)>0: return canonicals
    return 'Canonical name not found'

def getaliases(values):
    '''Get the alias names associated with a canonical name, given the canonical name'''
    if len(values) != 1: return 'getaliases-command accepts only one argument'
    aliases = []
    for (alias, canonical) in alias_dict:
        if canonical == values[0]:
            aliases.append(alias)
    if len(aliases)>0: return aliases
    return 'Alias name not found'

def getlist(values):
    '''Get the association's list between IP addresses and canonical names'''
    if len(values) != 0: return 'getlist-command accepts no arguments'
    records = []
    for ip, canonical in ip_dict.items():
        records.append(ip + ' ' + canonical)
    if len(records)>0: return records
    return 'No records within the database'

def getinverse(values):
    '''Get the canonical name associated with an IP address'''
    if len(values) != 1: return 'getinverse-command accepts only one argument'
    ip_ = checkIP(values[0])
    if ip_ == 'error': return 'Bad IP format'
    for ip, canonical in ip_dict.items():
        if ip == ip_:
            return canonical
    return 'Canonical name not found'

def setip(values):
    '''Set the association between IP address and canonical name'''
    if len(values) != 2: return 'setip-command accepts two arguments'
    ip_ = checkIP(values[0])
    if ip_ == 'error': return 'Bad IP format'
    for ip, canonical in ip_dict.items():
        if ip == ip_:
            return 'This IP address is already been used'
        if canonical == values[1]:
            return 'This canonical name is already been used'
    ip_dict[ip_] = values[1]
    return 'OK'

def update(values):
    '''Update the IP address associated with the given canonical name'''
    if len(values) != 2: return 'update-command accepts two arguments'
    ip_ = checkIP(values[0])
    if ip_ == 'error': return 'Bad IP format'
    for ip, canonical in ip_dict.items():
        if ip == ip_ and canonical == values[1]:
            return 'OK - This association already exists'
        elif ip == ip_ and not canonical == values[1]:
            return 'This IP address is associated with another canonical name'
        elif not ip == ip_ and canonical == values[1]:
            ip_dict[ip_] = values[1]
            del(ip_dict[ip])
            return 'OK'
    return setip(values)

def setalias(values):
    '''Set the association between an alias name and the canonical name'''
    if len(values) != 2: return 'setalias-command accepts two arguments'
    canonical_found = False
    alias_found = False
    for ip, canonical in ip_dict.items():
        if canonical == values[1]:
            canonical_found = True
    for (alias, canonical) in alias_dict:
        if canonical == values[1]:
            if alias == values[0]:
                alias_found = True
    if not canonical_found: return 'Canonical name not found'
    elif alias_found: return 'This alias is already configured'
    else:
        alias_dict.append((values[0], values[1]))
        return 'OK'

def rm(values):
    '''Remove the association between IP address and canonical name, given the canonical name. Remove from database all
    informations of IP address, canonical name and all the aliases associated with that canonical name'''
    if len(values) != 1: return 'rm-command accepts only one argument'
    canonical_found = False
    for ip, canonical in ip_dict.items():
        if canonical == values[0]:
            canonical_found = True
            del ip_dict[ip]
            break
    if canonical_found:
        alias_count = 0
        for index in range(len(alias_dict)-1, -1, -1):
            if alias_dict[index][1] == values[0]:
                del alias_dict[index]
                alias_count += 1
        return 'OK - Removed {} aliases'.format(alias_count)
    else:
        return 'Canonical name not found'

def rminverse(values):
    '''Same as rm-command but executes function given the IP address'''
    if len(values) != 1: return 'rminverse-command accepts only one argument'
    canonical_found = False
    canonical_name = ''
    ip_ = checkIP(values[0])
    if ip_ == 'error': return 'Bad IP format'
    for ip, canonical in ip_dict.items():
        if ip == ip_:
            canonical_found = True
            canonical_name = canonical
            del ip_dict[ip]
            break
    if canonical_found:
        alias_count = 0
        for index in range(len(alias_dict)-1, -1, -1):
            if alias_dict[index][1] == canonical_name:
                del alias_dict[index]
                alias_count += 1
        return 'OK - Removed {} aliases'.format(alias_count)
    else:
        return 'IP not found'

def rmalias(values):
    '''Remove the association between an alias name and a canonical name'''
    if len(values) != 2: return 'rmalias-command accepts two arguments'
    canonical_found = False
    alias_found = False
    for (alias, canonical) in alias_dict:
        if canonical == values[1]:
            canonical_found = True
            if alias == values[0]:
                alias_found = True
                alias_dict.remove((alias, canonical))
                break
    if not canonical_found:
        if not alias_found: return 'Canonical and alias name not found'
        return 'Canonical name not found'
    elif not alias_found: return 'Alias name not found'
    else: return 'OK'

def syntax(values):
    '''get commands descriptions'''
    if len(values) != 0: return 'syntax-command accepts no arguments'
    com = []
    com.append('GET - syntax: "get [canonicalName]", function: get IP address given the canonical name.')
    com.append('GETINVERSE - syntax: "getinverse [IPaddress]", function: get canonical name given the IP address.')
    com.append('GETCANONICALS - syntax: "getcanonicals [aliasName]", function: get canonical names given an alias name.')
    com.append('GETALIASES - syntax: "getaliases [canonicalName]", function: get aliases names given a canonical name.')
    com.append('GETLIST - syntax: "getlist", function: get full list of associations between IP addresses and canonical names.')
    com.append('SETIP - syntax: "setip [IPaddress] [canonicalName]", function: set the associations between IP address and canonical name.')
    com.append('UPDATE - syntax: "update [IPaddress] [canonicalName]", function: update IP address associated with a given canonical name. '+
               'This will assume the same function as setip-command if neither IP nor canonicalname are found.')
    com.append('SETALIAS - syntax: "setalias [aliasName] [canonicalName]", function: set the associations between alias name and canonical name.')
    com.append('RM - syntax: "rm [canonicalName]", function: remove the association between IP address and canonical name. '+
               'This will remove also every record containing one of the two attributes.')
    com.append('RMINVERSE - syntax: "rminverse [IPaddress]", function: same function as the rm-command but given the IP address.')
    com.append('RMALIAS - syntax: "rmalias [aliasName] [canonicalName]", function: remove the association between alias name and canonical name.')
    return com

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

def getHour():
    hour, min, sec = map(int, time.strftime("%H %M %S").split())
    if (hour < 10): hour = '0' + str(hour)
    if (min < 10): min = '0' + str(min)
    if (sec < 10): sec = '0' + str(sec)
    return '{}:{}:{}'.format(hour, min, sec)


if __name__ == '__main__':
    main()