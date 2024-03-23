import time
import traceback
import os
import paramiko
from paramiko.channel import Channel
from paramiko.ssh_exception import SSHException

# Generic system settings:
PORT = 22
prompt_ready = ["(textgen)", "$", "text-generation-webui"]  # All of these keywords need to be present
ip_getter = "ip a | grep 'enp1s0f0' | grep 'inet' | cut -d: -f2"

# Resources fetch command
resources_req = "srun -N 1 -c 4 -t TIME -p gpu --pty bash"

# For command crafting:
cuda_visible = "CUDA_VISIBLE_DEVICES=_DEVICE_ "
arguments = [
    "--model TheBloke_wizard-mega-13B-GPTQ",
    "--listen"
]
com_struct = "python server.py ARGUMENTS" \
             " --listen-port _PORT0_ --api-blocking-port _PORT1_ --api-streaming-port _PORT2_ --api"


# noinspection PyBroadException
class MySFTPClient(paramiko.SFTPClient):
    def __init__(self, sock: Channel):
        super().__init__(sock)
        self.ssh = None


def initialize_connection(host, user):
    # SSH CONNECTION TO HPC FRONT-END
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
    res_req = resources_req.replace('TIME', str(time_))
    channel.send(f"{res_req}\n")
    output = channel.recv(1024).decode()
    print(f'ALLOCATION OF RESOURCES')
    while output:
        print(output)
        if sum([0 if x in output else 1 for x in prompt_ready]) == 0:
            break
        output = channel.recv(1024).decode()


def start_llm(channel, ports):
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
    channel.send('ps -ef | grep -i cian_cl | grep python | cut -d " " -f 4 | '
                 'while read line ; do kill -9 "$line"; done\n')
    time.sleep(1)
    channel.send(command + "\n")
    output = channel.recv(1024).decode()
    print(f'START OF LLMs')
    print(output)
    output = " "
    while output:
        print(output)
        if sum([0 if x in output else 1 for x in prompt_ready]) == 0:
            break
        output = channel.recv(1024).decode()


# noinspection PyBroadException
def init(user, host, password, ports, time_):
    try:
        ssh, channel = initialize_connection(host, user)
        allocate_resources(ports, time_)
        start_llm(channel, ports)
    except Exception:
        print(traceback.format_exc())


if __name__ == '__main__':
    pass
