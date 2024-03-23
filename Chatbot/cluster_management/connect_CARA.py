import traceback
import os
import paramiko
from paramiko.channel import Channel
from paramiko.ssh_exception import SSHException

# Generic system settings:
PORT = 22
prompt_ready = []
ip_getter = "/usr/sbin/ifconfig eno1 | grep 'inet ' | cut -d: -f2"

# Resources fetch command
resources_req = "salloc -N 1 -c 4 --partition=rome-a100 --time=TIME:00"

# For command crafting:
cuda_visible = "CUDA_VISIBLE_DEVICES=_DEVICE_ "
arguments = [
    # "--model TheBloke_wizard-mega-13B-GPTQ",
    "--model CalderaAI_30B-Lazarus",
    "--listen"
]
com_struct = "python server.py ARGUMENTS" \
             " --listen-port _PORT0_ --api-blocking-port _PORT1_ --api-streaming-port _PORT2_ --api"


def initialize_connection(host, user):
    # SSH CONNECTION TO CARA FRONT-END
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    key = paramiko.RSAKey.from_private_key_file(os.path.expanduser('~/.ssh/id_rsa'))
    try:
        ssh.connect(host, PORT, user, pkey=key)
    except SSHException:
        raise SSHException('Impossible to establish the connection. ' +
                           'Check if you are logged into the DLR network')
    transport = paramiko.Transport((host, PORT))
    transport.connect(None, user, pkey=key)
    sftp = MySFTPClient.from_transport(transport)
    sftp.ssh = ssh

    channel = ssh.invoke_shell()
    output = channel.recv(1024).decode()
    while output:
        print(output)
        if sum([0 if x in output else 1 for x in prompt_ready]) == 0:
            break
        output = channel.recv(1024).decode()
    return ssh, channel


def allocate_resources(channel, time_):
    # ALLOCATION OF RESOURCES
    print(f'ALLOCATION OF RESOURCES')
    min = time_ % 60
    hours = time_ // 60
    form_time = f"{str(hours) if hours >= 10 else ('0' + str(hours))}:{str(min) if min >= 10 else ('0' + str(min))}"
    res_req = resources_req.replace('TIME', form_time)
    channel.send(f"{res_req}\n")
    output = channel.recv(1024).decode()
    while output:
        print(output)
        if sum([0 if x in output else 1 for x in prompt_ready]) == 0:
            break
        output = channel.recv(1024).decode()


def get_ip(channel):
    # GET inet IP ADDRESS OF THE NODE
    node_addr = ''
    channel.send(f"{ip_getter}\n")
    output = channel.recv(1024).decode()
    while output:
        print(output)
        l_out = output.split()
        l_out.reverse()
        if "inet" in l_out:
            node_addr = l_out[l_out.index('inet') - 1]
        if sum([0 if x in output else 1 for x in prompt_ready]) == 0:
            break
        output = channel.recv(1024).decode()
    if node_addr != "":
        print(f'NODE IP: {node_addr}')
    return node_addr


def notebook_tunneling(channel, node_addr):
    # SSH TUNNELING BETWEEN CARA FRONT-END AND COMPUTING NODE
    print(f"Tunneling for notebook")
    com = f"ssh -N -L localhost:8888:localhost:8888 {node_addr}\n"
    print(f"COMMAND: {com}")
    channel.send(com)


def tunneling(channel, ports, node_addr):
    # SSH TUNNELING BETWEEN CARA FRONT-END AND COMPUTING NODE
    com = "ssh -N "
    for port in ports:
        api_port = port + 1000
        stream_port = port + 2000
        com += f"-L localhost:{port}:localhost:{port} " \
               f"-L localhost:{api_port}:localhost:{api_port} " \
               f"-L localhost:{stream_port}:localhost:{stream_port} "
    com += f" {node_addr}\n"
    print(f"COMMAND: {com}")
    channel.send(com)


def start_llm(channel, ports):
    # CRAFTING COMMAND
    # The API ports have the same address as the ones defined above plus 1000 (for api) and 2000 (for streaming)
    command = "" if len(ports) == 1 else cuda_visible.replace('_DEVICE_', '0')
    for port, i in zip(ports, range(len(ports))):
        # CREATE COMMAND FOR THE COMPUTING NODE
        if i != 0:
            command += " & " + cuda_visible
        command = command.replace('_DEVICE_', str(i)) + " " + com_struct.replace('_PORT0_', str(port))\
            .replace('_PORT1_', str(port + 1000)).replace('_PORT2_', str(port + 2000)).\
            replace('ARGUMENTS', ' '.join(arguments))

    # START OF LLMs
    print(f'START OF LLMs')
    channel.send(command + "\n")
    output = channel.recv(1024).decode()
    while output:
        print(output)
        if sum([0 if x in output else 1 for x in prompt_ready]) == 0:
            break
        output = channel.recv(1024).decode()


def start_notebook(channel):
    print(''.join(['\n'] * 20))
    command = "jupyter notebook --ip='*' --NotebookApp.token='' --NotebookApp.password=''"
    # START OF Jupyter Notebook
    print(f'START OF Jupyter Notebook')
    channel.send(command + "\n")
    output = channel.recv(1024).decode()
    while output:
        print(output)
        if sum([0 if x in output else 1 for x in prompt_ready]) == 0:
            break
        output = channel.recv(1024).decode()


# noinspection PyBroadException
class MySFTPClient(paramiko.SFTPClient):
    def __init__(self, sock: Channel):
        super().__init__(sock)
        self.ssh = None


# noinspection PyBroadException
def jupyter_notebook(user, host, password, ports, time_):
    try:
        global prompt_ready
        prompt_ready = ["llama2]$"]  # All of these keywords need to be present
        ssh, channel = initialize_connection(host, user)
        allocate_resources(channel, time_)
        node_addr = get_ip(channel)
        channel0 = ssh.invoke_shell()
        notebook_tunneling(channel0, node_addr)
        start_notebook(channel)
    except Exception:
        print(traceback.format_exc())


# noinspection PyBroadException
def init(user, host, password, ports, time_):
    try:
        global prompt_ready
        prompt_ready = ["text-generation-webui]$"]  # All of these keywords need to be present
        ssh, channel = initialize_connection(host, user)
        allocate_resources(channel, time_)
        node_addr = get_ip(channel)
        channel0 = ssh.invoke_shell()
        tunneling(channel0, ports, node_addr)
        start_llm(channel, ports)
    except Exception:
        print(traceback.format_exc())


if __name__ == '__main__':
    pass
