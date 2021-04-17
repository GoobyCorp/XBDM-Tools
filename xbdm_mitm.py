#!/usr/bin/env python3

import socket
import asyncore
from shlex import shlex
from struct import unpack, pack
from collections import OrderedDict
from binascii import unhexlify, hexlify as _hexlify

# xbdm variables
XBDM_PORT = 730

# console variables
CONSOLE_IP = "0.0.0.1"

# socket variables
BUFF_SIZE = 2048

def hexlify(b: (bytes, bytearray)) -> str:
    return _hexlify(b).decode("utf8")

def format_command(command: (bytes, bytearray), lowercase: bool = False) -> str:
    command =  command.decode("utf8").rstrip()
    if lowercase:
        command = command.lower()
    return command

class XBDMShlex(shlex):
    def __init__(self, *args, **kwargs):
        super(XBDMShlex, self).__init__(*args, **kwargs)
        self.escape = ""  #remove the \ escape

class XBDMCommand(object):
    name = None
    args = OrderedDict()
    flags = []
    formatted = None

    def __init__(self):
        self.reset()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def reset(self) -> None:
        self.name = None
        self.args = OrderedDict()
        self.flags = []
        self.formatted = None

    @staticmethod
    def parse(command: str):
        sh = XBDMShlex(command, posix=True)
        sh.whitespace_split = True
        command = list(sh)
        cmd = XBDMCommand()
        cmd.set_name(command[0])
        if len(command) > 1:
            for single in command[1:]:
                if "=" in single:
                    (key, value) = single.split("=", 1)
                    cmd.add_param(key, value)
                else:
                    if not cmd.flag_exists(single):
                        cmd.add_flag(single)
        return cmd

    def set_name(self, name: str):
        self.name = name

    def set_response_code(self, code: int):
        self.name = str(code) + "-"

    def flag_exists(self, key: str) -> bool:
        return key in self.flags

    def param_exists(self, key: str, lc_check: bool = False) -> bool:
        return self.get_param(key, lc_check) is not None

    def add_flag(self, key: str):
        return self.flags.append(key)

    def add_param(self, key: str, value: (str, int, bytes, bytearray), quoted: bool = False) -> None:
        if isinstance(value, bytes) or isinstance(value, bytearray):
            value = str(value, "utf8")
        if quoted:
            value = "\"" + value + "\""
        if isinstance(value, int):
            value = "0x" + hexlify(pack(">I", value))
        self.args[key] = value

    def get_param(self, key: str, lc_check: bool = False) -> (None, str):
        val = self.args.get(key)
        if lc_check and val is None:
            val = self.args.get(key.lower())
        return val

    def get_output(self, as_bytes: bool = False, line_ending: bool = True) -> (str, bytes, bytearray):
        out_str = " ".join([(key + "=" + value) for (key, value) in self.args.items()])
        if self.name is not None:
            out_str = self.name + " " + out_str
        if line_ending:
            out_str += "\r\n"
        if as_bytes:
            return bytes(out_str, "utf8")
        self.reset()
        return out_str

class XBDMHandler(asyncore.dispatcher_with_send):
    client_addr: str = None
    client_port: int = None

    console_addr: str = None
    console_port: int = None

    console_sock: socket = None

    buff: (bytes, bytearray) = b""

    def set_addr(self, addr: str, port: int) -> None:
        self.client_addr = addr
        self.client_port = port

    def set_console(self, addr: str, port: int) -> None:
        self.console_addr = addr
        self.console_port = port

    def handle_read(self):
        raw_command = self.recv(BUFF_SIZE)
        if raw_command:
            if raw_command.endswith(b"\r\n"):
                fmt_cmd = format_command(raw_command)
                print(fmt_cmd)
                parsed = XBDMCommand.parse(format_command(raw_command))
                if parsed.name == "connected":
                    self.console_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.console_sock.connect((self.console_addr, self.console_port))
                    self.console_sock.send(raw_command)
                else:
                    self.console_sock.send(raw_command)
                response = self.console_sock.recv(BUFF_SIZE)
                self.buff += response

    def handle_write(self):
        if len(self.buff) > 0:
            self.send(self.buff[:BUFF_SIZE])
            self.buff = self.buff[BUFF_SIZE:]

class XBDMServer(asyncore.dispatcher):
    def __init__(self):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(("0.0.0.0", XBDM_PORT))
        self.listen(5)

    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            (sock, addr) = pair
            print("Incoming connection from %s:%s" % (addr[0], addr[1]))
            handler = XBDMHandler(sock)
            handler.set_addr(addr[0], addr[1])
            handler.set_console(CONSOLE_IP, XBDM_PORT)

if __name__ == "__main__":
    server = XBDMServer()
    asyncore.loop()