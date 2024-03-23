import getpass
import subprocess
import threading
import time
import connect_CARA
import connect_HPC


def get_pass():
    pass_w = ''
    if pass_w == '':
        pass_w = getpass.getpass('Type your user password: ')
    return pass_w


def tunneling_custom():
    return


def tunneling(pool):
    # SSH TUNNELING BETWEEN CLIENT AND CARA FRONT-END
    pool_ports = pool.get_cara_ports()
    if len(pool_ports) != 0:
        com = "ssh -N -L localhost:8888:localhost:8888 "
        for port in pool_ports:
            api_port = port + 1000
            api_stream_port = port + 2000
            com += f"-L localhost:{port}:localhost:{port} " \
                   f"-L localhost:{api_port}:localhost:{api_port} " \
                   f"-L localhost:{api_stream_port}:localhost:{api_stream_port} "
        com += "cian_cl@cara.dlr.de"
        print(f"COMMAND: {com}")
        proc = subprocess.Popen(com.split(' '), stdin=subprocess.PIPE, shell=True)
        time.sleep(2)


class Node:
    def __init__(self, ports):
        self.user = ""
        self.password = ""
        self.host = ""
        self.server_on = ""
        self.ports = ports
        self.api_ports = [x + 1000 for x in ports]
        self.api_stream_ports = [x + 2000 for x in ports]

    def initialize(self):
        print('initializing simple node')


class CaraNode(Node):
    def __init__(self, ports, allocation_time=20):
        super().__init__(ports)
        self.host = "cara.dlr.de"
        self.server_on = "localhost"
        self.allocation_time = int(allocation_time)

    def jupyter_notebook(self):
        connect_CARA.jupyter_notebook(self.user, self.host, self.password, self.ports, self.allocation_time)

    def initialize(self):
        connect_CARA.init(self.user, self.host, self.password, self.ports, self.allocation_time)


class HpcNode(Node):
    def __init__(self, ports, allocation_time=60):
        super().__init__(ports)
        self.host = "fe-store02.sc.bs.dlr.de"
        self.server_on = "129.247.34.81"
        self.allocation_time = int(allocation_time)

    def initialize(self):
        connect_HPC.init(self.user, self.host, self.password, self.ports, self.allocation_time)


class NodePool(list):
    def __init__(self, user, password, nodes):
        super().__init__()
        self.user = user
        self.password = password
        for node in nodes:
            self.append(node)
            node.user = self.user
            node.password = self.password

    def get_all_ports(self):
        ports = []
        for node in self:
            ports += node.ports
        return ports

    def get_cara_ports(self):
        ports = []
        for node in self:
            if node.__class__.__name__ == 'CaraNode':
                ports += node.ports
        return ports

    def jupyter_notebook(self):
        for node, i in zip(self, range(len(self))):
            threading.Thread(target=node.jupyter_notebook).start()

    def initialize(self, indexes):
        for node, i in zip(self, range(len(self))):
            if i in indexes:
                threading.Thread(target=node.initialize).start()

    def initialize_all(self):
        for node in self:
            threading.Thread(target=node.initialize).start()


if __name__ == '__main__':
    pass
