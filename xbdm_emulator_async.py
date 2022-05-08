#!/usr/bin/python3

import asyncio
from io import BytesIO
from typing import Any
from shlex import shlex
from shutil import rmtree
from json import load, dump
from calendar import timegm
from struct import unpack, pack
from collections import OrderedDict
from os import walk, rename, remove, makedirs
from os.path import isfile, isdir, join, getsize
from datetime import datetime, timedelta, tzinfo
from ctypes import Structure, Union, c_ulong, c_uint32, c_int32, c_uint64, c_int64

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

# config
cfg: list | dict = {}
jrpc2cfg: list | dict = {}

# Responses from the console are high to low
# PC data is read from low to high
# Big Endian    = high -> low
# Little Endian = low -> high

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

def list_dirs(path: str) -> tuple | list:
	return next(walk(path))[1]

def list_files(path: str) -> tuple | list:
	return next(walk(path))[2]

def list_drives() -> (list, tuple):
	return list_dirs(cfg["xbdm_dir"])

def xbdm_to_local_path(path: str) -> str:
	return join(cfg["xbdm_dir"], path.replace(":\\", "/").replace("\\", "/"))

def format_command(command: bytes | bytearray, lowercase: bool = False):
	command =  command.decode("utf8").rstrip()
	if lowercase:
		command = command.lower()
	return command

def bswap32(b: bytes | bytearray) -> bytes | bytearray:
	if len(b) % 4 == 0:
		return b"".join([bytes([b[x + 3], b[x + 2], b[x + 1], b[x]]) for x in range(0, len(b), 4)])

def uint32_to_uint64(low: str | int, high: str | int) -> int:
	if isinstance(low, str):
		low = unpack("!I", bytes.fromhex(low.replace("0x", "")))[0]
	if isinstance(high, str):
		high = unpack("!I", bytes.fromhex(high.replace("0x", "")))[0]
	return unpack("<Q", pack("<II", low, high))[0]

def uint64_to_uint32(num: int, as_hex: bool = False, as_bytes: bool = False) -> tuple | list:
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

def filetime_to_dt(ft) -> datetime:
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

def is_int(s: str) -> str | int:
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
		self.whitespace_split = True

class XBDMParam:
	def __init__(self, value: Any):
		self.value = value

	def __int__(self) -> int:
		return self.as_int()

	def __str__(self) -> str:
		return self.as_str()

	def __bytes__(self) -> bytes:
		return self.as_bytes()

	def is_none(self) -> bool:
		return self.value is None

	def as_int(self) -> int:
		if isinstance(self.value, str):
			if self.value.startswith("0x"):
				return unpack(">I", bytes.fromhex(self.value[2:]))[0]
		return int(self.value)

	def as_str(self) -> str:
		return str(self.value)

	def as_bytes(self) -> bytes:
		return bytes.fromhex(self.value)

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

	def set_name(self, name: str) -> None:
		self.name = name

	def set_response_code(self, code: int) -> None:
		self.name = str(code) + "-"

	def flag_exists(self, key: str) -> bool:
		return key in self.flags

	def param_exists(self, key: str, lc_check: bool = False) -> bool:
		return not self.get_param(key, lc_check).is_none()

	def add_flag(self, key: str) -> Any:
		return self.flags.append(key)

	def add_param(self, key: str, value: str | int | bytes | bytearray, quoted: bool = False) -> None:
		if isinstance(value, bytes) or isinstance(value, bytearray):
			value = str(value, "utf8")
		if quoted:
			value = "\"" + value + "\""
		if isinstance(value, int):
			value = "0x" + pack(">I", value).hex()
		self.args[key] = value

	def get_param(self, key: str, lc_check: bool = False) -> XBDMParam:
		val = self.args.get(key)
		if lc_check and val is None:
			val = self.args.get(key.lower())
		return XBDMParam(val)

	def get_output(self, as_bytes: bool = False, line_ending: bool = True) -> str | bytes | bytearray:
		out_str = " ".join([(key + "=" + value) for (key, value) in self.args.items()])
		if self.name is not None:
			out_str = self.name + " " + out_str
		if line_ending:
			out_str += "\r\n"
		if as_bytes:
			return bytes(out_str, "utf8")
		self.reset()
		return out_str

class XBDMServerProtocol(asyncio.Protocol):
	receiving_files = False
	num_files = 0
	num_files_left = 0
	file_data = b""
	file_data_left = 0
	file_size = 0
	file_path = ""
	file_step = 0

	client_addr: str = None
	client_port: int = None

	def send_single_line(self, line: str | bytes | bytearray) -> None:
		if isinstance(line, str):
			line = line.encode("ASCII")
		if not line.endswith(b"\r\n"):
			line += b"\r\n"
		self.transport.write(line)

	def start_multi_line(self) -> None:
		self.send_single_line("202- multiline response follows")

	def end_multi_line(self) -> None:
		self.send_single_line(".")

	def send_multi_line(self, lines: list[str | bytes | bytearray], start_stop: bool = True) -> None:
		if start_stop:
			self.start_multi_line()
		for line in lines:
			if isinstance(line, str):
				line = line.encode("UTF8")
			self.send_single_line(line)
		if start_stop:
			self.end_multi_line()

	def connection_made(self, transport: asyncio.ReadTransport | asyncio.WriteTransport):
		(self.client_addr, self.client_port) = transport.get_extra_info("peername")
		print(f"Incoming connection from {self.client_addr}:{self.client_port}")
		self.transport = transport
		self.send_single_line("201- connected")

	def connection_lost(self, ex):
		# print(f"Lost connection to {self.client_addr}:{self.client_port}")
		self.transport.close()

	def eof_received(self) -> bool | None:
		self.transport.close()

	def data_received(self, raw_command: bytes) -> None:
		# raw_command = self.recv(2048)
		if raw_command:
			if raw_command.endswith(b"\r\n") and not self.receiving_files:
				if cfg["debug"]:
					print(bytes(raw_command))
					print(raw_command.hex().upper())
				parsed = XBDMCommand.parse(format_command(raw_command))
				if parsed.name == "BOXID":
					print("Sending box ID...")
					self.send_single_line("420- box is not locked")
				elif parsed.name == "xbupdate!drawtext":
					self.send_single_line("200- OK")
				elif parsed.name == "xbupdate!version":
					self.send_single_line("200- OK")
				elif parsed.name == "xbupdate!validatehddpartitions":
					self.send_single_line("200- OK")
				elif parsed.name == "xbupdate!isflashclean":
					self.send_single_line("200- OK")
				elif parsed.name == "xbupdate!instrecoverytype":
					self.send_single_line("200- OK")
				elif parsed.name == "xbupdate!validdevice":
					self.send_single_line("200- OK")
				elif parsed.name == "recovery":
					print("Booting recovery...")
					self.send_single_line("200- OK")
				elif parsed.name == "DBGNAME":
					print("Sending console name...")
					self.send_single_line("200- " + cfg["console_name"])
				elif parsed.name == "consoletype":
					print("Sending console type...")
					self.send_single_line("200- " + cfg["console_type"])
				elif parsed.name == "consolefeatures":
					# Basic JRPC2 Support - Byrom
					if parsed.param_exists("ver") and parsed.param_exists("type"): # is jrpc2 command
						type_param = parsed.get_param("type").as_int()
						# type 0 to 8 are related to call function by the look of it
						#if type_param == "1": # example when loading a plugin
						#    print("JRPC2 - One of the call function commands received! Responding...")
						#    self.transport.write(b"200- 0\r\n") # 0 for load success
						if type_param == 9:
							print("JRPC2 - Resolve function command received! Responding...")
							self.send_single_line("200- 80067F48")
						elif type_param == 10:
							print("JRPC2 - Get CPUKey command received! Responding...")
							self.send_single_line("200- " + jrpc2cfg["CPUKey"])
						elif type_param == 11:
							print("JRPC2 - Shutdown console command received! Responding...")
							self.send_single_line("200- S_OK")
						elif type_param == 12:
							print("JRPC2 - XNotify command received! Responding...")
							# consolefeatures ver=2 type=12 params=\"A\0\A\2\2/37\53696D706C6520546F6F6C20436F6E6E656374656420546F20596F7572205472696E697479\1\34\"
							# 53696D706C6520546F6F6C20436F6E6E656374656420546F20596F7572205472696E697479 -> HexToText = Simple Tool Connected To Your Trinity
							self.send_single_line("200- S_OK")
						elif type_param == 13:
							print("JRPC2 - Get Kern Version command received! Responding...")
							self.send_single_line("200- " + jrpc2cfg["KernelVers"])
						elif type_param == 14:
							print("JRPC2 - Set ROL LED command received! Responding...") # multple options for this green red orange topleft topright bottomleft bottomright
							self.send_single_line("200- S_OK")
						elif type_param == 15:
							gettemp_params = parsed.get_param("params")
							print(gettemp_params)
							if gettemp_params == "A\\0\\A\\1\\1\\0\\":
								print("JRPC2 - Get CPU Temperature command received! Responding...")
								self.send_single_line("200- " + hex(jrpc2cfg["CPUTemp"]).replace("0x", ""))
							elif gettemp_params == "A\\0\\A\\1\\1\\1\\":
								print("JRPC2 - Get GPU Temperature command received! Responding...")
								self.send_single_line("200- " + hex(jrpc2cfg["GPUTemp"]).replace("0x", ""))
							elif gettemp_params == "A\\0\\A\\1\\1\\2\\":
								print("JRPC2 - Get EDRAM Temperature command received! Responding...")
								self.send_single_line("200- " + hex(jrpc2cfg["EDRAMTemp"]).replace("0x", ""))
							elif gettemp_params == "A\\0\\A\\1\\1\\3\\":
								print("JRPC2 - Get MOBO Temperature command received! Responding...")
								self.send_single_line("200- " + hex(jrpc2cfg["MOBOTemp"]).replace("0x", ""))
						elif type_param == 16:
							print("JRPC2 - Get TitleID command received! Responding...")
							self.send_single_line("200- " + jrpc2cfg["TitleID"])
						elif type_param == 17:
							print("JRPC2 - Get Mobo Type command received! Responding...")
							self.send_single_line("200- " + jrpc2cfg["MoboType"])
						elif type_param == 18:
							print("JRPC2 - Constant memory setting command received! Responding...")
							self.send_single_line("200- S_OK")
						else:
							print("JRPC2 - Unknown command received! Responding...") # catch any unknowns
							self.send_single_line("200- 0") # better than nothing / is the return when load plugin is called
					# end of jrpc2 commands
					else:
						print("Sending console features...")
						if parsed.param_exists("params"):  #extended query
							print("Feature Params: " + parsed.get_param("params").as_str())
							self.send_single_line("200- S_OK")
						else:  #simple query
							self.send_single_line("200- " + cfg["console_type"])
				elif parsed.name == "advmem" and parsed.flag_exists("status"):
					print("Sending memory properties...")
					self.send_single_line("200- enabled")
				elif parsed.name == "ALTADDR":
					print("Sending title IP address...")
					addr = bytes(map(int, cfg["alternate_address"].split('.'))).hex()
					self.send_single_line("200- addr=0x" + addr)
				elif parsed.name == "SYSTIME":
					print("Sending system time...")
					(time_low, time_high) = uint64_to_uint32(system_time(), True)
					with XBDMCommand() as cmd:
						cmd.set_response_code(200)
						cmd.add_param("high", time_high)
						cmd.add_param("low", time_low)
						cmd_data = cmd.get_output(True)
					self.transport.write(cmd_data)
				elif parsed.name == "systeminfo":
					print("Sending system info...")
					lines = [
						"HDD=" + "Enabled" if cfg["hdd_enabled"] else "Disabled",
						"Type=" + cfg["console_type"],
						f"Platform={cfg['platform']} System={cfg['system']}",
						f"BaseKrnl={cfg['base_kernel']} Krnl={cfg['kernel']} XDK={cfg['xdk']}"
					]
					self.send_multi_line(lines)
				elif parsed.name == "XBEINFO" and parsed.flag_exists("RUNNING"):
					print("Sending current title info...")
					lines = [
						"timestamp=0x00000000 checksum=0x00000000",
						f"name=\"{cfg['current_title_path']}\""
					]
					self.send_multi_line(lines)
				elif parsed.name == "screenshot":
					print("Sending screenshot...")
					self.transport.write(b"203- binary response follows\r\n")

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
						self.transport.write(cmd.get_output(True, True))
					self.transport.write(data)
				elif parsed.name == "DRIVELIST":
					print("Sending drive list...")
					self.send_multi_line([f"drivename=\"{x}\"" for x in list_drives()])
				elif parsed.name == "ISDEBUGGER":
					print("Requesting is debugger...")
					self.send_single_line("410- name=\"XRPC\" user=" + cfg["username"])
				elif parsed.name == "break" and parsed.flag_exists("clearall"):
					print("Removing all breakpoints...")
					self.send_single_line("200- OK")
				elif parsed.name == "MODULES":
					print("Sending module listing...")
					lines = []
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
						lines.append(cmd_data)
					self.send_multi_line(lines)
				elif parsed.name == "kdnet":  # kdnet config commands
					if parsed.flag_exists("set"):  # set kdnet settings
						if parsed.param_exists("IP") and parsed.param_exists("Port"):
							kdnet_addr = parsed.get_param("IP")
							kdnet_port = parsed.get_param("Port")
							print(f"Attempted to configure KDNET to talk to {kdnet_addr}:{kdnet_port}...")
							self.send_single_line("200- kdnet set succeeded.")
					elif parsed.flag_exists("show"):  # show settings
						self.send_single_line("200- kdnet settings:\x1E\tEnable=1\x1E\tTarget IP: 192.168.0.43\x1E\tTarget MAC: 00-25-AE-E4-43-87\x1E\tHost IP: 192.168.0.2\x1E\tHost Port: 50001\x1E\tEncrypted: 0\x1E")
				elif parsed.name == "DEBUGGER":
					if parsed.flag_exists("DISCONNECT"):
						print("Debugger disconnecting...")
					elif parsed.flag_exists("CONNECT"):
						print("Debugger connecting...")
						#dbg_port = int(parsed.get_param("PORT"))
						#dbg_name = parsed.get_param("user")
					self.send_single_line("200- OK")
				elif parsed.name == "DRIVEFREESPACE":
					if parsed.get_param("NAME"):
						drive_label = parsed.get_param("NAME")
						print(f"Requesting free space for drive label {drive_label}...")
						(low, high) = uint64_to_uint32(cfg["console_hdd_size"], True, True)
						with XBDMCommand() as cmd:
							cmd.add_param("freetocallerlo", low)
							cmd.add_param("freetocallerhi", high)
							cmd.add_param("totalbyteslo", low)
							cmd.add_param("totalbyteshi", high)
							cmd.add_param("totalfreebyteslo", low)
							cmd.add_param("totalfreebyteshi", high)
							cmd_data = cmd.get_output(True)
						self.send_multi_line([cmd_data])
				elif parsed.name == "DIRLIST":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME").as_str())
						if isdir(phys_path):
							print(f"Requesting directory listing for {phys_path}...")

							self.start_multi_line()
							lines = []
							for single in list_files(phys_path):
								single_path = join(phys_path, single)
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
								lines.append(cmd_data)
							self.send_multi_line(lines, False)

							lines = [f"name=\"{x}\" sizehi=0x0 sizelo=0x0 createhi=0x01d3c0d2 createlo=0x40667d00 changehi=0x01d3c0d2 changelo=0x40667d00 directory" for x in list_dirs(phys_path)]
							self.send_multi_line(lines, False)
							self.end_multi_line()
						else:
							self.send_single_line("402- directory not found")
				elif parsed.name == "SETFILEATTRIBUTES":
					self.send_single_line("200- OK")
				elif parsed.name == "GETFILEATTRIBUTES":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME").as_str())
						print(f"Requesting file attributes for \"{phys_path}\"...")
						if isfile(phys_path):
							print("File exists...")
							file_size = getsize(phys_path)
							(ctime_low, ctime_high) = uint64_to_uint32(creation_time_to_file_time(phys_path), True)
							(mtime_low, mtime_high) = uint64_to_uint32(modify_time_to_file_time(phys_path), True)
							(size_low, size_high) = uint64_to_uint32(file_size, True)
							with XBDMCommand() as cmd:
								cmd.add_param("sizehi", size_high)
								cmd.add_param("sizelo", size_low)
								cmd.add_param("createhi", ctime_high)
								cmd.add_param("createlo", ctime_low)
								cmd.add_param("changehi", mtime_high)
								cmd.add_param("changelo", mtime_low)
								cmd_data = cmd.get_output(True)
							self.send_multi_line([cmd_data])
						else:
							print("File doesn't exist...")
							self.send_single_line("402- file not found")
				elif parsed.name == "MKDIR":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME").as_str())
						if not isfile(phys_path) and not isdir(phys_path):
							print(f"Created directory \"{phys_path}\"...")
							makedirs(phys_path, exist_ok=True)
							self.send_single_line("200- OK")
				elif parsed.name == "GETFILE":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME").as_str())
						if isfile(phys_path):
							print(f"Sending file @ \"{phys_path}\"...")
							with open(phys_path, "rb") as f:
								data = f.read()
							self.transport.write(b"203- binary response follows\r\n")
							self.transport.write(pack("<I", len(data)))
							self.transport.write(data)
				elif parsed.name == "SENDVFILE":
					if parsed.param_exists("COUNT"):
						file_count = parsed.get_param("COUNT").as_int()
						print(f"Receiving {file_count} file(s)...")
						if file_count > 0:
							self.send_single_line("204- send binary data")
							self.receiving_files = True
							self.num_files = file_count
							self.num_files_left = file_count
							self.file_step = 0
							self.send_single_line("203- binary response follows")
							self.transport.write((b"\x00" * 4) * self.num_files)
				elif parsed.name == "SENDFILE":
					print("Receiving single file...")
					self.send_single_line("203- binary response follows")
					self.transport.write((b"\x00" * 4))
				elif parsed.name == "RENAME":
					if parsed.param_exists("NAME") and parsed.param_exists("NEWNAME"):
						old_file_path = xbdm_to_local_path(parsed.get_param("NAME").as_str())
						new_file_path = xbdm_to_local_path(parsed.get_param("NEWNAME").as_str())
						if isfile(old_file_path) or isdir(old_file_path):
							print(f"Renaming \"{old_file_path}\" to \"{new_file_path}\"...")
							rename(old_file_path, new_file_path)
							self.send_single_line("200- OK")
				elif parsed.name == "DELETE":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME").as_str())
						if parsed.flag_exists("DIR"):
							print(f"Deleting folder @ \"{phys_path}\"...")
							rmtree(phys_path, True)
						else:
							print(f"Deleting file @ \"{phys_path}\"...")
							remove(phys_path)
						self.send_single_line("200- OK")
				elif parsed.name == "setmem":
					if parsed.param_exists("addr") and parsed.param_exists("data"):
						print(parsed.get_param("addr"))
						setmem_addr = parsed.get_param("addr")
						setmem_data = bytes.fromhex(parsed.get_param("data").as_str())
						print(f"Attempted to set {len(setmem_data)} byte(s) @ {setmem_addr}...")
						self.send_single_line(f"200- set {str(len(setmem_data))} bytes")
				elif parsed.name == "GETMEM" or parsed.name == "GETMEMEX":
					if parsed.param_exists("ADDR") and parsed.param_exists("LENGTH"):
						addr = parsed.get_param("ADDR").as_int()
						length = parsed.get_param("LENGTH").as_int()
						# length = unpack("!I", bytes.fromhex(length.replace("0x", "")))[0]
						print(f"Attempted to get {length} byte(s) @ {addr}...")
						self.send_single_line("203- binary response follows")
						self.transport.write(pack("<H", 1024) + (b"suckcock" * 128))
						self.transport.write(pack("<H", 1024) + (b"suckcock" * 128))
						self.transport.write(pack("<H", 1024) + (b"suckcock" * 128))
						self.transport.write(pack("<H", 1024) + (b"suckcock" * 128))
				elif parsed.name == "setsystime":
					if parsed.param_exists("clocklo") and parsed.param_exists("clockhi") and parsed.param_exists("tz"):
						sys_time_low = parsed.get_param("clocklo")
						sys_time_high = parsed.get_param("clockhi")
						#timezone = bool(parsed.get_param("tz"))
						sys_time = uint32_to_uint64(sys_time_low, sys_time_high)
						print(f"Setting system time to {sys_time}...")
						self.send_single_line("200- OK")
				elif parsed.name == "NOTIFY" and parsed.param_exists("reconnectport") and parsed.flag_exists("reverse"):
					reconnect_port = int(parsed.get_param("reconnectport"))
					print(f"Requesting reconnect on TCP port {reconnect_port}...")
					self.send_single_line("205- now a notification channel")
				elif parsed.name == "notifyat":
					if parsed.flag_exists("drop"):
						self.send_single_line("200- OK")
				elif parsed.name == "LOCKMODE":
					if parsed.param_exists("BOXID"):
						box_id = parsed.get_param("BOXID")
						print(f"Attempted to lock system with box ID {box_id}...")
						self.send_single_line("200- OK")
					elif parsed.flag_exists("unlock"):
						print("Attempted to unlock system...")
						self.send_single_line("200- OK")
				elif parsed.name == "USER" and parsed.flag_exists("NAME"):
					if parsed.param_exists("NAME"):
						priv_user = parsed.get_param("NAME")
						priv_str = parsed.flags[-1]
						print(f"Attempted to add user {priv_user} to locked system with the privilege string \"{priv_str}\"...")
						self.send_single_line("200- OK")
				elif parsed.name == "magicboot":
					if parsed.param_exists("title") and parsed.param_exists("directory"):
						magicboot_exe = parsed.get_param("title")
						magicboot_dir = parsed.get_param("directory")
						print(f"Magic Boot attempted to run \"{magicboot_exe}\"")
						self.send_single_line("200- OK")
					else:
						print("Reboot attempted!")
						self.send_single_line("200- OK")
				elif parsed.name == "GETUSERPRIV":
					print("Sending user privilege")
					self.send_single_line("402- file not found")
				elif parsed.name == "BYE":
					print("Closing the socket...")
					self.send_single_line("200- bye")
					self.transport.close()
				else:
					if parsed.name is not None:
						print("UNHANDLED COMMAND: " + parsed.name)
			elif raw_command == bytes.fromhex("020405B40103030801010402"):
				print("Sending unknown?")
				self.transport.write(raw_command)
			elif self.receiving_files:
				if self.num_files_left > 0 and self.file_step == 0:
					# print("Size:", len(raw_command))
					# print(raw_command.hex())
					#receive file header
					with BytesIO(raw_command) as bio:
						header_size = unpack("!I", bio.read(4))[0]
						# print("Header Size:", header_size)
						header = bio.read(header_size - 4)  # exclude header size
						(createhi, createlo, modifyhi, modifylo, file_size_hi, file_size_lo, file_attrbs) = unpack("!IIIIIIL", header[:28])

						self.file_size = uint32_to_uint64(file_size_lo, file_size_hi)
						self.file_path = xbdm_to_local_path(header[28:-1].decode("UTF8"))
						self.file_data += bio.read()
						self.file_data_left = self.file_size - len(self.file_data)

					self.file_step = 1
				elif self.file_step == 1 and self.num_files_left > 0 and len(self.file_data) > 0 and self.file_data_left > 0:
					self.file_data += raw_command
					self.file_data_left -= len(raw_command)

				if self.file_data_left == 0:
					print(f"File written to \"{self.file_path}\"...")
					with open(self.file_path, "wb") as f:
						f.write(self.file_data)

					self.file_step = 0
					self.num_files_left -= 1
					self.file_data_left = 0
					self.file_size = 0
					self.file_path = ""
					self.file_data = b""

				if self.num_files_left == 0:
					print(f"{self.num_files} file transfer(s) complete!")
					self.send_single_line("203- binary response follows")
					self.transport.write((b"\x00" * 4) * self.num_files)
					self.num_files = 0
					self.receiving_files = False

async def run_server():
	loop = asyncio.get_running_loop()
	server = await loop.create_server(XBDMServerProtocol, "0.0.0.0", XBDM_PORT)
	async with server:
		await server.serve_forever()

def main() -> int:
	global cfg, jrpc2cfg

	if isfile(CONFIG_FILE):
		cfg = load(open(CONFIG_FILE, "r"))
	else:
		cfg = {"xbdm_dir": "XBDM"}
		dump(cfg, open(CONFIG_FILE, "w"))

	if isfile(JRPC2_CONFIG_FILE):
		jrpc2cfg = load(open(JRPC2_CONFIG_FILE, "r"))
	else:
		jrpc2cfg = {
			"MoboType": "Trinity",
			"CPUKey": "13371337133713371337133713371337",
			"KernelVers": "17559",
			"TitleID": "FFFE07D1",
			"CPUTemp": 45,
			"GPUTemp": 44,
			"EDRAMTemp": 43,
			"MOBOTemp": 39
		}
		dump(jrpc2cfg, open(JRPC2_CONFIG_FILE, "w"))

	asyncio.run(run_server())

	return 0

if __name__ == "__main__":
	exit(main())