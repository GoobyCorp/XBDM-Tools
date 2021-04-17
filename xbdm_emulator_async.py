#!/usr/bin/python3

import socket
import asyncore
from math import floor
from io import BytesIO
from shlex import shlex
from shutil import rmtree
from ctypes import c_uint32
from json import load, dump
from calendar import timegm
from struct import unpack, pack
from collections import OrderedDict
from os import walk, rename, remove, makedirs
from os.path import isfile, isdir, join, getsize
from datetime import datetime, timedelta, tzinfo
from ctypes import Structure, Union, c_ulong, c_int32, c_uint64, c_int64

# constants
D3DFMT_A8R8G8B8 = 0x18280186
D3DFMT_A2R10G10B10 = 0x18280192

# ctypes aliases
c_dword = c_ulong

# xbdm variables
XBDM_PORT = 730

# config variables
CONFIG_FILE = "config.json"

# JRPC2 variables - Byrom
JRPC2_CONFIG_FILE = "jrpc2_config.json"

# time variables
EPOCH_AS_FILETIME = 116444736000000000
HUNDREDS_OF_NANOSECONDS = 10000000
ZERO = timedelta(0)
HOUR = timedelta(hours=1)

#Responses from the console are high to low
#PC data is read from low to high
#Big Endian    = high -> low
#Little Endian = low -> high

class INT64_PART(Structure):
    _pack_ = 1
    _fields_ = [
        ("Low", c_int32),
        ("High", c_int32)
    ]

class UINT64_PART(Structure):
    _pack_ = 1
    _fields_ = [
        ("Low", c_uint32),
        ("High", c_uint32)
    ]

class INT64(Union):
    _pack_ = 1
    _fields_ = [
        ("a", INT64_PART),
        ("Quad", c_int64)
    ]

class UINT64(Union):
    _pack_ = 1
    _fields_ = [
        ("a", UINT64_PART),
        ("Quad", c_uint64)
    ]

class FileInfo(Structure):
    _fields_ = [
        ("dwSize", c_uint32),
        ("CreateTime", INT64),
        ("ChangeTime", INT64),
        ("FileSize", INT64),
        ("FileAttributes", c_uint32)
    ]

def list_dirs(path: str) -> (list, tuple):
    return next(walk(path))[1]

def list_files(path: str) -> (list, tuple):
    return next(walk(path))[2]

def list_drives() -> (list, tuple):
    return list_dirs(cfg["xbdm_dir"])

def xbdm_to_local_path(path: str) -> str:
    return join(cfg["xbdm_dir"], path.replace(":\\", "/").replace("\\", "/"))

def format_command(command: (bytes, bytearray), lowercase: bool = False):
    command =  command.decode("utf8").rstrip()
    if lowercase:
        command = command.lower()
    return command

def bswap32(b: (bytes, bytearray)) -> (bytes, bytearray):
    if len(b) % 4 == 0:
        return b"".join([bytes([b[x + 3], b[x + 2], b[x + 1], b[x]]) for x in range(0, len(b), 4)])

def uint32_to_uint64(low: (str, int), high: (str, int)) -> int:
    if isinstance(low, str):
        low = unpack("!I", bytes.fromhex(low.replace("0x", "")))[0]
    if isinstance(high, str):
        high = unpack("!I", bytes.fromhex(high.replace("0x", "")))[0]
    return unpack("<Q", pack("<II", low, high))[0]

def uint64_to_uint32(num: int, as_hex: bool = False, as_bytes: bool = False) -> (tuple, list):
    i = unpack("<II", pack("<Q", num))
    if as_hex:
        low = "0x" + pack("!I", i[0]).hex()
        high = "0x" + pack("!I", i[1]).hex()
        if as_bytes:
            return [bytes(low, "utf8"), bytes(high, "utf8")]
        return [low, high]
    return i

def dt_to_filetime(dt):
    if (dt.tzinfo is None) or (dt.tzinfo.utcoffset(dt) is None):
        dt = dt.replace(tzinfo=UTC())
    ft = EPOCH_AS_FILETIME + (timegm(dt.timetuple()) * HUNDREDS_OF_NANOSECONDS)
    return ft + (dt.microsecond * 10)

def filetime_to_dt(ft):
    # Get seconds and remainder in terms of Unix epoch
    (s, ns100) = divmod(ft - EPOCH_AS_FILETIME, HUNDREDS_OF_NANOSECONDS)
    # Convert to datetime object
    dt = datetime.utcfromtimestamp(s)
    # Add remainder in as microseconds. Python 3.2 requires an integer
    dt = dt.replace(microsecond=(ns100 // 10))
    return dt

def creation_time_to_file_time(path: str) -> int:
    #dt = datetime.utcfromtimestamp(getctime(path))
    return dt_to_filetime(datetime.utcnow())

def modify_time_to_file_time(path: str) -> int:
    #dt = datetime.utcfromtimestamp(getmtime(path))
    return dt_to_filetime(datetime.utcnow())

def system_time() -> int:
    dt1 = datetime(1, 1, 1, 23, 0, 0)
    dt2 = datetime.utcnow()
    return int(abs(dt2 - dt1).total_seconds()) * 10000000

def is_int(s: str) -> (str, int):
    try:
        return int(s)
    except:
        return s

class UTC(tzinfo):
    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO

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
            value = "0x" + pack(">I", value).hex()
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
    client_addr = None

    #file variables
    receiving_files = False
    num_files = 0
    num_files_left = 0
    file_data = b""
    file_data_left = 0
    file_size = 0
    file_path = ""
    file_step = 0

    def set_addr(self, addr: str) -> None:
        self.client_addr = addr

    def handle_read(self):
        raw_command = self.recv(2048)
        if raw_command:
            if raw_command.endswith(b"\r\n") and not self.receiving_files:
                if cfg["debug"]:
                    print(raw_command)
                parsed = XBDMCommand.parse(format_command(raw_command))
                if parsed.name == "BOXID":
                    print("Sending box ID...")
                    self.send(b"420- box is not locked\r\n")
                elif parsed.name == "xbupdate!drawtext":
                    self.send(b"200- OK\r\n")
                elif parsed.name == "xbupdate!version":
                    self.send(b"200- OK\r\n")
                elif parsed.name == "xbupdate!validatehddpartitions":
                    self.send(b"200- OK\r\n")
                elif parsed.name == "xbupdate!isflashclean":
                    self.send(b"200- OK\r\n")
                elif parsed.name == "xbupdate!instrecoverytype":
                    self.send(b"200- OK\r\n")
                elif parsed.name == "xbupdate!validdevice":
                    self.send(b"200- OK\r\n")
                elif parsed.name == "recovery":
                    print("Booting recovery...")
                    self.send(b"200- OK\r\n")
                elif parsed.name == "DBGNAME":
                    print("Sending console name...")
                    self.send(b"200- " + bytes(cfg["console_name"], "utf8") + b"\r\n")
                elif parsed.name == "consoletype":
                    print("Sending console type...")
                    self.send(b"200- " + bytes(cfg["console_type"], "utf8") + b"\r\n")
                elif parsed.name == "consolefeatures":
                    # Basic JRPC2 Support - Byrom
                    if parsed.param_exists("ver") and parsed.param_exists("type"): # is jrpc2 command
                        type_param = int(parsed.get_param("type"))
                        # type 0 to 8 are related to call function by the look of it
                        #if type_param == "1": # example when loading a plugin
                        #    print("JRPC2 - One of the call function commands received! Responding...")
                        #    self.send(b"200- 0\r\n") # 0 for load success
                        if type_param == 9:
                            print("JRPC2 - Resolve function command received! Responding...")
                            self.send(b"200- 80067F48\r\n") # address of the requested function
                        elif type_param == 10:
                            print("JRPC2 - Get CPUKey command received! Responding...")
                            self.send(b"200- " + bytes(jrpc2cfg["CPUKey"], "utf8") + b"\r\n")
                        elif type_param == 11:
                            print("JRPC2 - Shutdown console command received! Responding...")
                            self.send(b"200- S_OK\r\n")
                        elif type_param == 12:
                            print("JRPC2 - XNotify command received! Responding...")
                            # consolefeatures ver=2 type=12 params=\"A\0\A\2\2/37\53696D706C6520546F6F6C20436F6E6E656374656420546F20596F7572205472696E697479\1\34\"
                            # 53696D706C6520546F6F6C20436F6E6E656374656420546F20596F7572205472696E697479 -> HexToText = Simple Tool Connected To Your Trinity
                            self.send(b"200- S_OK\r\n")
                        elif type_param == 13:
                            print("JRPC2 - Get Kern Version command received! Responding...")
                            self.send(b"200- " + bytes(jrpc2cfg["KernelVers"], "utf8") + b"\r\n")
                        elif type_param == 14:
                            print("JRPC2 - Set ROL LED command received! Responding...") # multple options for this green red orange topleft topright bottomleft bottomright
                            self.send(b"200- S_OK\r\n")
                        elif type_param == 15:
                            gettemp_params = parsed.get_param("params")
                            print(gettemp_params)
                            if gettemp_params == "A\\0\\A\\1\\1\\0\\":
                                print("JRPC2 - Get CPU Temperature command received! Responding...")
                                self.send(b"200- " + bytes(hex(jrpc2cfg["CPUTemp"]).replace("0x",""), "utf8") + b"\r\n")
                            elif gettemp_params == "A\\0\\A\\1\\1\\1\\":
                                print("JRPC2 - Get GPU Temperature command received! Responding...")
                                self.send(b"200- " + bytes(hex(jrpc2cfg["GPUTemp"]).replace("0x",""), "utf8") + b"\r\n")
                            elif gettemp_params == "A\\0\\A\\1\\1\\2\\":
                                print("JRPC2 - Get EDRAM Temperature command received! Responding...")
                                self.send(b"200- " + bytes(hex(jrpc2cfg["EDRAMTemp"]).replace("0x",""), "utf8") + b"\r\n")
                            elif gettemp_params == "A\\0\\A\\1\\1\\3\\":
                                print("JRPC2 - Get MOBO Temperature command received! Responding...")
                                self.send(b"200- " + bytes(hex(jrpc2cfg["MOBOTemp"]).replace("0x",""), "utf8") + b"\r\n")
                        elif type_param == 16:
                            print("JRPC2 - Get TitleID command received! Responding...")
                            self.send(b"200- " + bytes(jrpc2cfg["TitleID"], "utf8") + b"\r\n")
                        elif type_param == 17:
                            print("JRPC2 - Get Mobo Type command received! Responding...")
                            self.send(b"200- " + bytes(jrpc2cfg["MoboType"], "utf8") + b"\r\n")
                        elif type_param == 18:
                            print("JRPC2 - Constant memory setting command received! Responding...")
                            self.send(b"200- S_OK\r\n")
                        else:
                            print("JRPC2 - Unknown command received! Responding...") # catch any unknowns
                            self.send(b"200- 0\r\n") # better than nothing / is the return when load plugin is called
                    # end of jrpc2 commands        
                    else:
                        print("Sending console features...")
                        if parsed.param_exists("params"):  #extended query
                            print("Feature Params: " + parsed.get_param("params"))
                            self.send(b"200- S_OK\r\n")
                        else:  #simple query
                            self.send(b"200- " + bytes(cfg["console_type"], "utf8") + b"\r\n")
                elif parsed.name == "advmem" and parsed.flag_exists("status"):
                    print("Sending memory properties...")
                    self.send(b"200- enabled\r\n")
                elif parsed.name == "ALTADDR":
                    print("Sending title IP address...")
                    addr = bytes(map(int, cfg["alternate_address"].split('.'))).hex()
                    self.send(b"200- addr=0x" + bytes(addr, "UTF8") + b"\r\n")
                elif parsed.name == "SYSTIME":
                    print("Sending system time...")
                    (time_low, time_high) = uint64_to_uint32(system_time(), True)
                    with XBDMCommand() as cmd:
                        cmd.set_response_code(200)
                        cmd.add_param("high", time_high)
                        cmd.add_param("low", time_low)
                        cmd_data = cmd.get_output(True)
                    self.send(cmd_data)
                elif parsed.name == "systeminfo":
                    print("Sending system info...")
                    self.send(b"202- multiline response follows\r\n")
                    lines = [
                        "HDD=" + "Enabled" if cfg["hdd_enabled"] else "Disabled",
                        "Type=" + cfg["console_type"],
                        "Platform=" + cfg["platform"] + " System=" + cfg["system"],
                        "BaseKrnl=" + cfg["base_kernel"] + " Krnl=" + cfg["kernel"] + " XDK=" + cfg["xdk"]
                    ]
                    for single in lines:
                        self.send(bytes(single, "utf8") + b"\r\n")
                    self.send(b".\r\n")
                elif parsed.name == "XBEINFO" and parsed.flag_exists("RUNNING"):
                    print("Sending current title info...")
                    self.send(b"202- multiline response follows\r\n")
                    self.send(b"timestamp=0x00000000 checksum=0x00000000\r\n")
                    self.send(b"name=\"" + bytes(cfg["current_title_path"], "utf8") + b"\"\r\n")
                    self.send(b".\r\n")
                elif parsed.name == "screenshot":
                    print("Sending screenshot...")
                    self.send(b"203- binary response follows\r\n")

                    # output resolution
                    ow = 1280  # 1280
                    oh = 720   # 720

                    # screen resolution
                    sw = 1920  # 1920
                    sh = 1080  # 1080

                    vw = ow
                    vh = oh
                    if vw % 128 != 0:
                        vw += (128 - vw % 128)
                    if vh % 128 != 0:
                        vh += (128 - vh % 128)
                    # pitch
                    p = ow * 4

                    with open(cfg["screenshot_file"], "rb") as f:
                        # read and send the file
                        data = f.read()


                    with XBDMCommand() as cmd:
                        cmd.add_param("pitch", p)
                        cmd.add_param("width", ow)
                        cmd.add_param("height", oh)
                        cmd.add_param("format", D3DFMT_A8R8G8B8)
                        cmd.add_param("offsetx", 0)
                        cmd.add_param("offsety", 0)
                        cmd.add_param("framebuffersize", len(data))  # 0x398000
                        cmd.add_param("sw", sw)
                        cmd.add_param("sh", sh)
                        cmd.add_param("colorspace", 0)
                        self.send(cmd.get_output(True, True))
                    self.send(data)
                elif parsed.name == "DRIVELIST":
                    print("Sending drive list...")
                    self.send(b"202- multiline response follows\r\n")
                    for single in list_drives():
                        # print("-Added %s!" % (single))
                        self.send(b"drivename=\"" + bytes(single, "utf8") + b"\"\r\n")
                    self.send(b".\r\n")
                elif parsed.name == "ISDEBUGGER":
                    print("Requesting is debugger...")
                    self.send(b"410- name=\"XRPC\" user=" + bytes(cfg["username"], "utf8") + b"\r\n")
                elif parsed.name == "break" and parsed.flag_exists("clearall"):
                    print("Removing all breakpoints...")
                    self.send(b"200- OK\r\n")
                elif parsed.name == "MODULES":
                    print("Sending module listing...")
                    self.send(b"202- multiline response follows\r\n")
                    for single in cfg["modules"]:
                        with XBDMCommand() as cmd:
                            cmd.add_param("name", single["name"], True)
                            cmd.add_param("base", single["base"])
                            cmd.add_param("size", single["size"])
                            cmd.add_param("check", 0)
                            cmd.add_param("timestamp", 0)
                            cmd.add_param("pdata", 0)
                            cmd.add_param("psize", 0)
                            cmd.add_param("thread", 0)
                            cmd.add_param("osize", 0)
                            cmd_data = cmd.get_output(True)
                        self.send(cmd_data)
                    self.send(b".\r\n")
                elif parsed.name == "kdnet":  # kdnet config commands
                    if parsed.flag_exists("set"):  # set kdnet settings
                        if parsed.param_exists("IP") and parsed.param_exists("Port"):
                            kdnet_addr = parsed.get_param("IP")
                            kdnet_port = parsed.get_param("Port")
                            print("Attempted to configure KDNET to talk to %s:%s..." % (kdnet_addr, kdnet_port))
                            self.send(b'200- kdnet set succeeded.\r\n')
                    elif parsed.flag_exists("show"):  # show settings
                        self.send(b'200- kdnet settings:\x1E\tEnable=1\x1E\tTarget IP: 192.168.0.43\x1E\tTarget MAC: 00-25-AE-E4-43-87\x1E\tHost IP: 192.168.0.2\x1E\tHost Port: 50001\x1E\tEncrypted: 0\x1E\r\n')
                elif parsed.name == "DEBUGGER":
                    if parsed.flag_exists("DISCONNECT"):
                        print("Debugger disconnecting...")
                    elif parsed.flag_exists("CONNECT"):
                        print("Debugger connecting...")
                        #dbg_port = int(parsed.get_param("PORT"))
                        #dbg_name = parsed.get_param("user")
                    self.send(b"200- OK\r\n")
                elif parsed.name == "DRIVEFREESPACE":
                    if parsed.get_param("NAME"):
                        drive_label = parsed.get_param("NAME")
                        print("Requesting free space for drive label %s..." % (drive_label))
                        self.send(b"202- multiline response follows\r\n")
                        (low, high) = uint64_to_uint32(cfg["console_hdd_size"], True, True)
                        with XBDMCommand() as cmd:
                            cmd.add_param("freetocallerlo", low)
                            cmd.add_param("freetocallerhi", high)
                            cmd.add_param("totalbyteslo", low)
                            cmd.add_param("totalbyteshi", high)
                            cmd.add_param("totalfreebyteslo", low)
                            cmd.add_param("totalfreebyteshi", high)
                            cmd_data = cmd.get_output(True)
                        self.send(cmd_data)
                        self.send(b".\r\n")
                elif parsed.name == "DIRLIST":
                    if parsed.param_exists("NAME"):
                        physical_path = xbdm_to_local_path(parsed.get_param("NAME"))
                        if isdir(physical_path):
                            print("Requesting directory listing for %s..." % (physical_path))
                            self.send(b"202- multiline response follows\r\n")
                            for single in list_files(physical_path):
                                single_path = join(physical_path, single)
                                single_size = getsize(single_path)
                                (ctime_low, ctime_high) = uint64_to_uint32(creation_time_to_file_time(single_path), True)
                                (mtime_low, mtime_high) = uint64_to_uint32(modify_time_to_file_time(single_path), True)
                                (size_low, size_high) = uint64_to_uint32(single_size, True)
                                with XBDMCommand() as cmd:
                                    cmd.add_param("name", single, True)
                                    cmd.add_param("sizehi", size_high)
                                    cmd.add_param("sizelo", size_low)
                                    cmd.add_param("createhi", ctime_high)
                                    cmd.add_param("createlo", ctime_low)
                                    cmd.add_param("changehi", mtime_high)
                                    cmd.add_param("changelo", mtime_low)
                                    cmd_data = cmd.get_output(True, True)
                                self.send(cmd_data)
                            for single in list_dirs(physical_path):
                                single = bytes(single, "utf8")
                                self.send(b"name=\"" + single + b"\" sizehi=0x0 sizelo=0x0 createhi=0x01d3c0d2 createlo=0x40667d00 changehi=0x01d3c0d2 changelo=0x40667d00 directory\r\n")
                            self.send(b".\r\n")
                        else:
                            self.send(b"402- directory not found\r\n")
                elif parsed.name == "SETFILEATTRIBUTES":
                    self.send(b"200- OK\r\n")
                elif parsed.name == "GETFILEATTRIBUTES":
                    if parsed.param_exists("NAME"):
                        physical_path = xbdm_to_local_path(parsed.get_param("NAME"))
                        print("Requesting file attributes for \"%s\"..." % (physical_path))
                        if isfile(physical_path):
                            print("File exists...")
                            file_size = getsize(physical_path)
                            (ctime_low, ctime_high) = uint64_to_uint32(creation_time_to_file_time(physical_path), True)
                            (mtime_low, mtime_high) = uint64_to_uint32(modify_time_to_file_time(physical_path), True)
                            (size_low, size_high) = uint64_to_uint32(file_size, True)
                            with XBDMCommand() as cmd:
                                cmd.add_param("sizehi", size_high)
                                cmd.add_param("sizelo", size_low)
                                cmd.add_param("createhi", ctime_high)
                                cmd.add_param("createlo", ctime_low)
                                cmd.add_param("changehi", mtime_high)
                                cmd.add_param("changelo", mtime_low)
                                cmd_data = cmd.get_output(True)
                            self.send(b"202- multiline response follows\r\n")
                            self.send(cmd_data)
                            self.send(b".\r\n")
                        else:
                            print("File doesn't exist...")
                            self.send(b"402- file not found\r\n")
                elif parsed.name == "MKDIR":
                    if parsed.param_exists("NAME"):
                        physical_path = xbdm_to_local_path(parsed.get_param("NAME"))
                        if not isfile(physical_path) and not isdir(physical_path):
                            print("Created directory \"%s\"..." % (physical_path))
                            makedirs(physical_path, exist_ok=True)
                            self.send(b"200- OK\r\n")
                elif parsed.name == "GETFILE":
                    if parsed.param_exists("NAME"):
                        physical_path = xbdm_to_local_path(parsed.get_param("NAME"))
                        if isfile(physical_path):
                            print("Sending file @ \"%s\"..." % (physical_path))
                            with open(physical_path, "rb") as f:
                                data = f.read()
                            self.send(b"203- binary response follows\r\n")
                            self.send(pack("<I", len(data)))
                            self.send(data)
                elif parsed.name == "SENDVFILE":
                    if parsed.param_exists("COUNT"):
                        file_count = parsed.get_param("COUNT")
                        print("Receiving %s file(s)..." % (file_count))
                        if file_count > 0:
                            self.send(b"204- send binary data\r\n")
                            #self.receiving_files = True
                            self.num_files = file_count
                            self.num_files_left = file_count
                            self.file_step = 0
                            self.send(b"203- binary response follows\r\n")
                            self.send((b"\x00" * 4) * self.num_files)
                elif parsed.name == "SENDFILE":
                    print("Receiving single file...")
                    self.send(b"204- send binary data\r\n")
                    #self.receiving_files = True
                    self.send(b"203- binary response follows\r\n")
                    self.send((b"\x00" * 4))
                elif parsed.name == "RENAME":
                    if parsed.param_exists("NAME") and parsed.param_exists("NEWNAME"):
                        old_file_path = xbdm_to_local_path(parsed.get_param("NAME"))
                        new_file_path = xbdm_to_local_path(parsed.get_param("NEWNAME"))
                        if isfile(old_file_path) or isdir(old_file_path):
                            print("Renaming \"%s\" to \"%s\"..." % (old_file_path, new_file_path))
                            rename(old_file_path, new_file_path)
                            self.send(b"200- OK\r\n")
                elif parsed.name == "DELETE":
                    if parsed.param_exists("NAME"):
                        physical_path = xbdm_to_local_path(parsed.get_param("NAME"))
                        if parsed.flag_exists("DIR"):
                            print("Deleting folder @ \"%s\"..." % (physical_path))
                            rmtree(physical_path, True)
                        else:
                            print("Deleting file @ \"%s\"..." % (physical_path))
                            remove(physical_path)
                        self.send(b"200- OK\r\n")
                elif parsed.name == "setmem":
                    if parsed.param_exists("addr") and parsed.param_exists("data"):
                        print(parsed.get_param("addr"))
                        setmem_addr = parsed.get_param("addr")
                        setmem_data = bytes.fromhex(parsed.get_param("data"))
                        print("Attempted to set %s byte(s) @ %s..." % (len(setmem_data), setmem_addr))
                        self.send(b"200- set " + bytes(str(len(setmem_data)), "UTF8") + b" bytes\r\n")
                elif parsed.name == "GETMEM" or parsed.name == "GETMEMEX":
                    if parsed.param_exists("ADDR") and parsed.param_exists("LENGTH"):
                        addr = parsed.get_param("ADDR")
                        length = parsed.get_param("LENGTH")
                        length = unpack("!I", bytes.fromhex(length.replace("0x", "")))[0]
                        print("Attempted to get %s byte(s) @ %s..." % (length, addr))
                        self.send(b"203- binary response follows\r\n")
                        self.send(pack("<H", 1024) + (b"suckcock" * 128))
                        self.send(pack("<H", 1024) + (b"suckcock" * 128))
                        self.send(pack("<H", 1024) + (b"suckcock" * 128))
                        self.send(pack("<H", 1024) + (b"suckcock" * 128))
                elif parsed.name == "setsystime":
                    if parsed.param_exists("clocklo") and parsed.param_exists("clockhi") and parsed.param_exists("tz"):
                        sys_time_low = parsed.get_param("clocklo")
                        sys_time_high = parsed.get_param("clockhi")
                        #timezone = bool(parsed.get_param("tz"))
                        sys_time = uint32_to_uint64(sys_time_low, sys_time_high)
                        print("Setting system time to %s..." % (sys_time))
                        self.send(b"200- OK\r\n")
                elif parsed.name == "NOTIFY" and parsed.param_exists("reconnectport") and parsed.flag_exists("reverse"):
                    reconnect_port = int(parsed.get_param("reconnectport"))
                    print("Requesting reconnect on TCP port %s..." % (reconnect_port))
                    self.send(b"205- now a notification channel\r\n")
                elif parsed.name == "notifyat":
                    if parsed.flag_exists("drop"):
                        self.send(b"200- OK\r\n")
                elif parsed.name == "LOCKMODE":
                    if parsed.param_exists("BOXID"):
                        box_id = parsed.get_param("BOXID")
                        print("Attempted to lock system with box ID %s..." % (box_id))
                        self.send(b"200- OK\r\n")
                    elif parsed.flag_exists("unlock"):
                        print("Attempted to unlock system...")
                        self.send(b"200- OK\r\n")
                elif parsed.name == "USER" and parsed.flag_exists("NAME"):
                    if parsed.param_exists("NAME"):
                        priv_user = parsed.get_param("NAME")
                        priv_str = parsed.flags[-1]
                        print("Attempted to add user %s to locked system with the privilege string \"%s\"..." % (priv_user, priv_str))
                        self.send(b"200- OK\r\n")
                elif parsed.name == "magicboot":
                    if parsed.param_exists("title") and parsed.param_exists("directory"):
                        magicboot_exe = parsed.get_param("title")
                        magicboot_dir = parsed.get_param("directory")
                        print("Magic Boot attempted to run \"%s\"" % (magicboot_exe))
                        self.send(b"200- OK\r\n")
                    else:
                        print("Reboot attempted!")
                        self.send(b"200- OK\r\n")
                elif parsed.name == "GETUSERPRIV":
                    print("Sending user privilege")
                    self.send(b"402- file not found\r\n")
                elif parsed.name == "BYE":
                    print("Closing the socket...")
                    self.send(b"200- bye\r\n")
                    self.close()
                else:
                    if parsed.name is not None:
                        print("UNHANDLED COMMAND: " + parsed.name)
            elif raw_command == bytes.fromhex("020405B40103030801010402"):
                print("Sending unknown?")
                self.send(raw_command)
            """
            elif self.receiving_files:
                if self.num_files_left > 0 and self.file_step == 0:
                    #receive file header
                    bio = BytesIO(raw_command)
                    header_size = unpack("!I", bio.read(4))[0]
                    header = bio.read(header_size - 4)  #exclude header size
                    (createhi, createlo, modifyhi, modifylo, file_size_hi, file_size_lo, file_attributes) = unpack("!IIIIIIL", header[:28])
                    self.file_size = uint32_to_uint64(file_size_lo, file_size_hi)
                    self.file_path = xbdm_to_local_path(str(header[28:-1], "utf8"))
                    self.file_data += bio.read()
                    bio.close()
                    self.file_data_left = self.file_size - len(self.file_data)

                    buff_size = 1024
                    count = int(floor(self.file_data_left / buff_size))
                    for x in range(0, count + 1):
                        if self.file_data_left <= 0:
                            self.file_data_left = 0
                            print("Fuck!")
                            break
                        if self.file_data_left < buff_size:
                            data = self.socket.recv(self.file_data_left)
                        else:
                            data = self.socket.recv(buff_size)
                        self.file_data += data
                        self.file_data_left -= len(data)
                        #print("%s / %s byte(s) left" % (self.file_data_left, self.file_size))

                if self.num_files_left > 0 and len(self.file_data) > 0 and self.file_data_left == 0:
                    print("File written to \"%s\"..." % (self.file_path))
                    open(self.file_path, "wb").write(self.file_data)
                    self.file_size = 0
                    self.file_data = b""
                    self.file_data_left = 0
                    self.file_path = ""
                    self.num_files_left -= 1

                if self.num_files_left == 0:
                    print("%s file transfer(s) complete!" % (self.num_files))
                    self.send(b"203- binary response follows\r\n")
                    self.send((b"\x00" * 4) * self.num_files)
                    self.num_files = 0
                    self.receiving_files = False
            """

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
            handler.set_addr(addr)
            sock.send(b"201- connected\r\n")


if __name__ == "__main__":
    if isfile(CONFIG_FILE):
        cfg = load(open(CONFIG_FILE, "r"))
    else:
        cfg = {"xbdm_dir": "XBDM"}
        dump(cfg, open(CONFIG_FILE, "w"))

    if isfile(JRPC2_CONFIG_FILE):
        jrpc2cfg = load(open(JRPC2_CONFIG_FILE, "r"))
    else:
        jrpc2cfg = {"MoboType": "Trinity",
        "CPUKey": "13371337133713371337133713371337",
        "KernelVers": "17559",
        "TitleID": "FFFE07D1",
        "CPUTemp": 45,
        "GPUTemp": 44,
        "EDRAMTemp": 43,
        "MOBOTemp": 39
        }
        dump(jrpc2cfg, open(JRPC2_CONFIG_FILE, "w"))

    server = XBDMServer()
    asyncore.loop()