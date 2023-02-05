#!/usr/bin/python3

import re
import asyncio
from io import BytesIO
from shlex import shlex
from enum import IntEnum
from pathlib import Path
from shutil import rmtree
from json import load, dump
from calendar import timegm
from struct import unpack, pack
from typing import Any, BinaryIO
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
XBDM_DIR = "DEVICES"

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

# regex
CODE_EXP = re.compile(r"^(\d+)-")

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

class ReceiveFileType(IntEnum):
	NONE = 0
	XBUPDATE_SINGLE = 1
	SENDFILE_SINGLE = 2
	SENDVFILE_MULTIPLE = 3

def list_dirs(path: str) -> tuple | list:
	return next(walk(path))[1]

def list_files(path: str) -> tuple | list:
	return next(walk(path))[2]

def list_drives() -> (list, tuple):
	return list_dirs("DEVICES/Harddisk0/Partition1/")

def xbdm_to_local_path(path: str) -> str:
	p = Path("DEVICES/Harddisk0/Partition1/")
	p /= path.replace(":\\", "/").replace("\\", "/")
	p = p.absolute()
	p.parent.mkdir(parents=True, exist_ok=True)
	return str(p)

	# return join("DEVICES/Harddisk0/Partition1/", path.replace(":\\", "/").replace("\\", "/")).replace("\\", "/")

def xbdm_to_device_path(path: str) -> str:
	if path.startswith("\\Device\\"):
		path = path[len("\\Device\\"):]
	elif path.startswith("\\"):
		path = path[1:]

	p = Path(XBDM_DIR)
	p /= path.replace(":\\", "/").replace("\\", "/")
	p = p.absolute()
	p.parent.mkdir(parents=True, exist_ok=True)
	return str(p)

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
		kwargs["posix"] = True
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
				return int.from_bytes(bytes.fromhex(self.value[2:].rjust(8, "0")), "big")
		return int(self.value)

	def as_bool(self) -> bool:
		return self.as_str().lower() in ["true", "1"]

	def as_str(self) -> str:
		return str(self.value)

	def as_bytes(self) -> bytes:
		return bytes.fromhex(self.value)

class XBDMCommand:
	name = None
	code = 0
	args = dict()
	flags = []
	formatted = None

	def __init__(self):
		self.reset()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		pass

	def __bytes__(self) -> bytes:
		return self.get_output(True)

	def reset(self) -> None:
		self.name = None
		self.code = 0
		self.args = dict()
		self.flags = []
		self.formatted = None

	@staticmethod
	def parse(command: str):
		sh = XBDMShlex(command)
		command = list(sh)
		cmd = XBDMCommand()
		match = CODE_EXP.match(command[0])
		if match:  # response
			cmd.set_code(int(match.group(1)))
		else:  # command
			cmd.set_name(command[0])
		if len(command) > 1:
			for single in command[1:]:
				if "=" in single:
					(key, value) = single.split("=", 1)
					cmd.set_param(key, value)
				else:
					if not cmd.flag_exists(single):
						cmd.set_flag(single)
		return cmd

	def set_name(self, name: str) -> None:
		self.name = name

	def set_code(self, code: int) -> None:
		# self.name = str(code) + "-"
		self.code = code

	def get_code(self) -> int:
		return self.code

	def get_flags(self) -> list[str]:
		return self.flags

	def flag_exists(self, key: str) -> bool:
		return key.lower() in self.flags

	def param_exists(self, key: str, lc_check: bool = False) -> bool:
		return not self.get_param(key, lc_check).is_none()

	def set_flag(self, key: str) -> Any:
		return self.flags.append(key.lower())

	def set_param(self, key: str, value: str | int | bytes | bytearray | bool, quoted: bool = False) -> XBDMParam:
		key = key.lower()
		if isinstance(value, bytes) or isinstance(value, bytearray):
			value = value.decode("UTF8")
		elif quoted:
			value = "\"" + value + "\""
		elif isinstance(value, str):
			value = value
		elif isinstance(value, int):
			if 0 <= value <= 0xFFFFFFFF:
				value = "0x" + value.to_bytes(4, "big").hex()
			elif 0 <= value <= 0xFFFFFFFFFFFFFFFF:
				value = "0x" + value.to_bytes(8, "big").hex()
		elif isinstance(value, bool):
			value = "1" if value else "0"
		self.args[key] = value
		return XBDMParam(value)

	def get_params(self) -> dict:
		return self.args

	def get_param(self, key: str, lc_check: bool = False) -> XBDMParam:
		key = key.lower()
		val = self.args.get(key)
		if lc_check and val is None:
			val = self.args.get(key)
		return XBDMParam(val)

	def get_output(self, as_bytes: bool = False, line_ending: bool = True) -> str | bytes | bytearray:
		o = ""
		if self.name is not None:  # commands only
			o = self.name
		if self.code is not None and self.code != 0:  # replies only
			o = str(self.code) + "-"
		if len(self.args) > 0:
			o += " "
			o += " ".join([(key + "=" + value) for (key, value) in self.args.items()])
		if len(self.flags) > 0:
			o += " "
			o += " ".join(self.flags)
		if line_ending:
			o += "\r\n"
		if as_bytes:
			return o.encode("UTF8")
		# self.reset()
		return o

class XBDMServerProtocol(asyncio.Protocol):
	# file transfer variables
	# single file
	receiving_file: bool = False
	file_cksm: int = 0

	# multiple files
	receiving_files: bool = False
	num_files_total: int = 0
	num_files_left: int = 0
	file_data_left: int = 0

	# both
	receiving_type: ReceiveFileType = ReceiveFileType.NONE
	file_path: str = ""
	file_handle: BinaryIO | None = None

	# client connection info
	client_addr: str = None
	client_port: int = None

	def reset(self) -> None:
		# file transfer variables
		# single file
		self.receiving_file = False
		self.file_cksm = 0

		# multiple files
		self.receiving_files = False
		self.num_files_total = 0
		self.num_files_left = 0
		self.file_data_left = 0

		# both
		self.receiving_type = ReceiveFileType.NONE
		self.file_path = ""
		self.file_handle = None

		# client connection info
		self.client_addr = None
		self.client_port = None

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
		self.reset()

		(self.client_addr, self.client_port) = transport.get_extra_info("peername")
		print(f"Incoming connection from {self.client_addr}:{self.client_port}")
		self.transport = transport
		self.send_single_line("201- connected")

	def connection_lost(self, ex):
		# print(ex)
		# print(f"Lost connection to {self.client_addr}:{self.client_port}")
		# self.transport.close()
		# self.transport = None
		pass

	def eof_received(self) -> bool:
		self.transport.close()
		self.transport = None
		return True

	def data_received(self, raw_command: bytes) -> None:
		if not raw_command:
			return

		if raw_command.endswith(b"\r\n") and not (self.receiving_file or self.receiving_files):
			if cfg["debug"]:
				print(bytes(raw_command))
				print(raw_command.hex().upper())
			parsed = XBDMCommand.parse(format_command(raw_command))
			match parsed.name.lower():
				case "boxid":
					print("Sending box ID...")
					self.send_single_line("420- box is not locked")
				case "xbupdate!drawtext":
					self.send_single_line("200- OK")
					print("xbupdate!drawtext")
				case "xbupdate!version":
					self.send_single_line("200- verhi=0x20000 verlo=0x53080012 platform=wi basesysversion=0x20445100 cursysversion=0x20445100 recstate=0x1")
					print("xbupdate!version")
				case "xbupdate!validatehddpartitions":
					self.send_single_line("200- OK")
					print("xbupdate!validatehddpartitions")
				case"xbupdate!isflashclean":
					self.send_single_line("200- OK")
					print("xbupdate!isflashclean")
				case "xbupdate!instrecoverytype":
					self.send_single_line("recoverytype=5 hresult=0x00000491")
					print("xbupdate!instrecoverytype")
				case "xbupdate!configure":
					self.send_single_line("200- OK")
					print("xbupdate!configure")
				case "xbupdate!validdevice":
					self.send_single_line("200- valid=1 deviceindex=1")
					print("xbupdate!validdevice")
				case "xbupdate!recovery":
					self.send_single_line("200- OK")
					print("xbupdate!recovery")
				case "xbupdate!sysfileupd":
					print("xbupdate!sysfileupd")
					file_name = parsed.get_param("name").as_str()
					file_path = xbdm_to_device_path(file_name)
					if parsed.param_exists("remove") and parsed.get_param("remove").as_bool():  # deleting file
						print(f"Deleting file \"{file_name}\"...")
						if isfile(file_path):
							remove(file_path)
						self.send_single_line("200- OK")
					elif parsed.param_exists("removedir") and parsed.get_param("removedir").as_bool():  # deleting directory
						print(f"Deleting directory \"{file_name}\"...")
						if isdir(file_path):
							rmtree(file_path, True)
						self.send_single_line("200- OK")
					elif parsed.param_exists("size"):  # receiving file
						file_size = parsed.get_param("size").as_int()
						print(f"Receiving single file \"{file_name}\" (0x{file_size:X})...")
						print(f"0x{parsed.get_param('crc').as_int():X}")
						self.send_single_line("204- send binary data")
						self.file_data_left = file_size
						self.file_cksm = parsed.get_param("crc").as_int()
						self.receiving_file = True
						self.receiving_type = ReceiveFileType.XBUPDATE_SINGLE
						self.file_path = file_path
					elif not parsed.param_exists("localsrc"):
						print(f"Modifying file \"{file_name}\"...")
						self.send_single_line("200- OK")
					elif parsed.param_exists("localsrc"):
						file_name_old = parsed.get_param("localsrc").as_str()
						file_path_old = xbdm_to_device_path(file_name_old)
						print(f"Modifying file \"{file_name_old}\" -> \"{file_name}\"...")
						self.send_single_line("200- OK")
				case "xbupdate!flash":
					self.send_single_line("200- OK")
					print("xbupdate!flash")
				case "xbupdate!commitsysextramdisk":
					self.send_single_line("200- result=0x10000000")
					print("xbupdate!commitsysextramdisk")
				case "xbupdate!getregion":
					self.send_single_line("200- region=0xFF")
					print("xbupdate!getregion")
				case "xbupdate!setxamfeaturemask":
					self.send_single_line("200- OK")
					print("xbupdate!setxamfeaturemask")
				case "xbupdate!close":
					self.send_single_line("200- OK")
					print("xbupdate!close")
				case "xbupdate!finish":
					self.send_single_line("200- OK")
					print("xbupdate!finish")
				case "xbupdate!restart":
					self.send_single_line("200-  ")
					print("xbupdate!restart")
				case "recovery":
					print("Booting recovery...")
					self.send_single_line("200- OK")
				case "dbgname":
					print("Sending console name...")
					self.send_single_line("200- " + cfg["console_name"])
				case "consoletype":
					print("Sending console type...")
					self.send_single_line("200- " + cfg["console_type"])
				case "consolefeatures":
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
				case "advmem":
					if parsed.flag_exists("status"):
						print("Sending memory properties...")
						self.send_single_line("200- enabled")
				case "altaddr":
					print("Sending title IP address...")
					addr = bytes(map(int, cfg["alternate_address"].split('.'))).hex()
					self.send_single_line("200- addr=0x" + addr)
				case "systime":
					print("Sending system time...")
					(time_low, time_high) = uint64_to_uint32(system_time(), True)
					with XBDMCommand() as cmd:
						cmd.set_code(200)
						cmd.set_param("high", time_high)
						cmd.set_param("low", time_low)
						cmd_data = cmd.get_output(True)
					self.transport.write(cmd_data)
				case "systeminfo":
					print("Sending system info...")
					lines = [
						"HDD=" + "Enabled" if cfg["hdd_enabled"] else "Disabled",
						"Type=" + cfg["console_type"],
						f"Platform={cfg['platform']} System={cfg['system']}",
						f"BaseKrnl={cfg['base_kernel']} Krnl={cfg['kernel']} XDK={cfg['xdk']}"
					]
					self.send_multi_line(lines)
				case "xbeinfo":
					if parsed.flag_exists("RUNNING"):
						print("Sending current title info...")
						lines = [
							"timestamp=0x00000000 checksum=0x00000000",
							f"name=\"{cfg['current_title_path']}\""
						]
						self.send_multi_line(lines)
				case "screenshot":
					print("Sending screenshot...")
					self.send_single_line("203- binary response follows")

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
						cmd.set_param("pitch", p)
						cmd.set_param("width", ow)
						cmd.set_param("height", oh)
						cmd.set_param("format", D3DFMT_A8R8G8B8)
						cmd.set_param("offsetx", 0)
						cmd.set_param("offsety", 0)
						cmd.set_param("framebuffersize", len(data))  # 0x398000
						cmd.set_param("sw", sw)
						cmd.set_param("sh", sh)
						cmd.set_param("colorspace", 0)
						self.transport.write(cmd.get_output(True, True))
					self.transport.write(data)
				case "drivelist":
					print("Sending drive list...")
					self.send_multi_line([f"drivename=\"{x}\"" for x in list_drives()])
				case "isdebugger":
					print("Requesting is debugger...")
					self.send_single_line("410- name=\"XRPC\" user=" + cfg["username"])
				case "break":
					if parsed.flag_exists("clearall"):
						print("Removing all breakpoints...")
						self.send_single_line("200- OK")
				case "modules":
					print("Sending module listing...")
					lines = []
					for single in cfg["modules"]:
						with XBDMCommand() as cmd:
							cmd.set_param("name", single["name"], True)
							cmd.set_param("base", single["base"])
							cmd.set_param("size", single["size"])
							cmd.set_param("check", 0)
							cmd.set_param("timestamp", 0)
							cmd.set_param("pdata", 0)
							cmd.set_param("psize", 0)
							cmd.set_param("thread", 0)
							cmd.set_param("osize", 0)
							cmd_data = cmd.get_output(True)
						lines.append(cmd_data)
					self.send_multi_line(lines)
				case "kdnet":  # kdnet config commands
					if parsed.flag_exists("set"):  # set kdnet settings
						if parsed.param_exists("IP") and parsed.param_exists("Port"):
							kdnet_addr = parsed.get_param("IP")
							kdnet_port = parsed.get_param("Port")
							print(f"Attempted to configure KDNET to talk to {kdnet_addr}:{kdnet_port}...")
							self.send_single_line("200- kdnet set succeeded.")
					elif parsed.flag_exists("show"):  # show settings
						self.send_single_line("200- kdnet settings:\x1E\tEnable=1\x1E\tTarget IP: 192.168.0.43\x1E\tTarget MAC: 00-25-AE-E4-43-87\x1E\tHost IP: 192.168.0.2\x1E\tHost Port: 50001\x1E\tEncrypted: 0\x1E")
				case "debugger":
					if parsed.flag_exists("DISCONNECT"):
						print("Debugger disconnecting...")
					elif parsed.flag_exists("CONNECT"):
						print("Debugger connecting...")
						#dbg_port = int(parsed.get_param("PORT"))
						#dbg_name = parsed.get_param("user")
					self.send_single_line("200- OK")
				case "drivefreespace":
					if parsed.get_param("NAME"):
						drive_label = parsed.get_param("NAME")
						print(f"Requesting free space for drive label {drive_label}...")
						(low, high) = uint64_to_uint32(cfg["console_hdd_size"], True, True)
						with XBDMCommand() as cmd:
							cmd.set_param("freetocallerlo", low)
							cmd.set_param("freetocallerhi", high)
							cmd.set_param("totalbyteslo", low)
							cmd.set_param("totalbyteshi", high)
							cmd.set_param("totalfreebyteslo", low)
							cmd.set_param("totalfreebyteshi", high)
							cmd_data = cmd.get_output(True)
						self.send_multi_line([cmd_data])
				case "dirlist":
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
									cmd.set_param("name", single, True)
									cmd.set_param("sizehi", size_high)
									cmd.set_param("sizelo", size_low)
									cmd.set_param("createhi", ctime_high)
									cmd.set_param("createlo", ctime_low)
									cmd.set_param("changehi", mtime_high)
									cmd.set_param("changelo", mtime_low)
									cmd_data = cmd.get_output(True, True)
								lines.append(cmd_data)
							self.send_multi_line(lines, False)

							lines = [f"name=\"{x}\" sizehi=0x0 sizelo=0x0 createhi=0x01d3c0d2 createlo=0x40667d00 changehi=0x01d3c0d2 changelo=0x40667d00 directory" for x in list_dirs(phys_path)]
							self.send_multi_line(lines, False)
							self.end_multi_line()
						else:
							self.send_single_line("402- directory not found")
				case "setfileattributes":
					self.send_single_line("200- OK")
				case "getfileattributes":
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
								cmd.set_param("sizehi", size_high)
								cmd.set_param("sizelo", size_low)
								cmd.set_param("createhi", ctime_high)
								cmd.set_param("createlo", ctime_low)
								cmd.set_param("changehi", mtime_high)
								cmd.set_param("changelo", mtime_low)
								cmd_data = cmd.get_output(True)
							self.send_multi_line([cmd_data])
						else:
							print("File doesn't exist...")
							self.send_single_line("402- file not found")
				case "mkdir":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME").as_str())
						if not isfile(phys_path) and not isdir(phys_path):
							print(f"Created directory \"{phys_path}\"...")
							makedirs(phys_path, exist_ok=True)
							self.send_single_line("200- OK")
				case "getfile":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME").as_str())
						if isfile(phys_path):
							print(f"Sending file @ \"{phys_path}\"...")
							with open(phys_path, "rb") as f:
								data = f.read()
							self.transport.write(b"203- binary response follows\r\n")
							self.transport.write(pack("<I", len(data)))
							self.transport.write(data)
				case "sendvfile":
					if parsed.param_exists("COUNT"):
						file_count = parsed.get_param("COUNT").as_int()
						print(f"Receiving {file_count} file(s)...")
						if file_count > 0:
							self.send_single_line("204- send binary data")
							self.num_files_total = file_count
							self.num_files_left = file_count
							self.receiving_files = True
							self.send_single_line("203- binary response follows")
							self.transport.write((b"\x00" * 4) * self.num_files_total)
				case "sendfile":
					file_name = parsed.get_param("NAME").as_str()
					file_size = parsed.get_param("LENGTH").as_int()
					print(f"Receiving single file \"{file_name}\" (0x{file_size:X})...")
					self.send_single_line("204- send binary data")
					self.file_data_left = file_size
					self.receiving_file = True
					self.receiving_type = ReceiveFileType.SENDFILE_SINGLE
					self.file_path = xbdm_to_device_path(file_name)
				case "rename":
					if parsed.param_exists("NAME") and parsed.param_exists("NEWNAME"):
						old_file_path = xbdm_to_local_path(parsed.get_param("NAME").as_str())
						new_file_path = xbdm_to_local_path(parsed.get_param("NEWNAME").as_str())
						if isfile(old_file_path) or isdir(old_file_path):
							print(f"Renaming \"{old_file_path}\" to \"{new_file_path}\"...")
							rename(old_file_path, new_file_path)
							self.send_single_line("200- OK")
				case "delete":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME").as_str())
						if parsed.flag_exists("DIR"):
							print(f"Deleting folder @ \"{phys_path}\"...")
							rmtree(phys_path, True)
						else:
							print(f"Deleting file @ \"{phys_path}\"...")
							remove(phys_path)
						self.send_single_line("200- OK")
				case "setmem":
					if parsed.param_exists("addr") and parsed.param_exists("data"):
						print(parsed.get_param("addr"))
						setmem_addr = parsed.get_param("addr")
						setmem_data = parsed.get_param("data").as_bytes()
						print(f"Attempted to set {len(setmem_data)} byte(s) @ {setmem_addr}...")
						self.send_single_line(f"200- set {str(len(setmem_data))} bytes")
				case "getmem" | "getmemex":
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
				case "setsystime":
					if parsed.param_exists("clocklo") and parsed.param_exists("clockhi") and parsed.param_exists("tz"):
						sys_time_low = parsed.get_param("clocklo").as_int()
						sys_time_high = parsed.get_param("clockhi").as_int()
						#timezone = bool(parsed.get_param("tz"))
						sys_time = uint32_to_uint64(sys_time_low, sys_time_high)
						print(f"Setting system time to {sys_time}...")
						self.send_single_line("200- OK")
				case "notify":
					if parsed.param_exists("reconnectport") and parsed.flag_exists("reverse"):
						reconnect_port = int(parsed.get_param("reconnectport"))
						print(f"Requesting reconnect on TCP port {reconnect_port}...")
						self.send_single_line("205- now a notification channel")
				case "notifyat":
					if parsed.flag_exists("drop"):
						self.send_single_line("200- OK")
				case "lockmode":
					if parsed.param_exists("BOXID"):
						box_id = parsed.get_param("BOXID")
						print(f"Attempted to lock system with box ID {box_id}...")
						self.send_single_line("200- OK")
					elif parsed.flag_exists("unlock"):
						print("Attempted to unlock system...")
						self.send_single_line("200- OK")
				case "user":
					if parsed.param_exists("name"):
						priv_user = parsed.get_param("NAME")
						print(f"Attempted to add user {priv_user} to locked system with the privilege string \"{' '.join(parsed.flags)}\"...")
						self.send_single_line("200- OK")
				case "userlist":
					self.send_multi_line([
						"name=\"John\" read write control config manage"
					])
				case "keyxchg":
					self.send_single_line("200- OK")
				case "magicboot":
					if parsed.param_exists("title") and parsed.param_exists("directory"):
						magicboot_exe = parsed.get_param("title")
						magicboot_dir = parsed.get_param("directory")
						print(f"Magic Boot attempted to run \"{magicboot_exe}\"")
						self.send_single_line("200- OK")
					else:
						print("Reboot attempted!")
						self.send_single_line("200- OK")
				case "getuserpriv":
					print("Sending user privilege")
					self.send_single_line("402- file not found")
				case "bye":
					# print("Closing the socket...")
					self.send_single_line("200- bye")
					self.transport.close()
				case _:
					if parsed.name is not None:
						print(f"UNHANDLED COMMAND \"{parsed.name}\"")
		elif raw_command == bytes.fromhex("020405B40103030801010402"):
			print("Sending unknown?")
			self.transport.write(raw_command)
		elif self.receiving_file:
			if self.file_handle is None:
				self.file_handle = open(self.file_path, "wb")
				self.file_data_left -= self.file_handle.write(raw_command)
			else:
				self.file_data_left -= self.file_handle.write(raw_command)

			if self.file_data_left == 0:
				self.file_handle.close()
				self.file_handle = None
				self.file_path = ""
				self.receiving_file = False

				if self.receiving_type == ReceiveFileType.SENDFILE_SINGLE:
					self.send_single_line("203- binary response follows")
					self.transport.write((b"\x00" * 4))
				elif self.receiving_type == ReceiveFileType.XBUPDATE_SINGLE:
					self.send_single_line("200- OK")
				self.receiving_type = ReceiveFileType.NONE
		elif self.receiving_files:
			if self.num_files_left > 0 and self.file_handle is None and self.file_data_left == 0:  # process header and first file bit
				# print("Size:", len(raw_command))
				# print(raw_command.hex())
				# receive file header
				with BytesIO(raw_command) as bio:
					(header_size,) = unpack(">I", bio.read(4))
					# print("Header Size:", header_size)
					header = bio.read(header_size - 4)  # exclude header size
					(create_hi, create_lo, modify_hi, modify_lo, file_size_hi, file_size_lo, file_attrbs) = unpack(">6IL", header[:28])

					file_size = uint32_to_uint64(file_size_lo, file_size_hi)
					self.file_path = xbdm_to_local_path(header[28:-1].decode("UTF8"))

					self.file_handle = open(self.file_path, "wb")
					self.file_handle.write(bio.read())

					self.file_data_left = file_size - self.file_handle.tell()
			elif self.num_files_left > 0 and self.file_handle is not None and self.file_data_left > 0:
				if self.file_data_left < len(raw_command):  # fragmented packet
					self.file_handle.write(raw_command[:self.file_data_left])

					self.file_handle.close()
					self.file_handle = None
					self.num_files_left -= 1
					self.file_path = ""
					raw_command = raw_command[self.file_data_left:]
					self.file_data_left = 0
					# send to data_received to process the packet
					self.data_received(raw_command)
					# return so it doesn't fall through
					return
				else:  # >= len(raw_command)unfragmented packet
					self.file_handle.write(raw_command)
					self.file_data_left -= len(raw_command)

			# close the handle and reset the download file's variables
			if self.file_data_left == 0:
				self.file_handle.close()
				self.file_handle = None
				self.num_files_left -= 1
				self.file_data_left = 0
				self.file_path = ""

			if self.num_files_left == 0:
				self.send_single_line("203- binary response follows")
				self.transport.write((b"\x00" * 4) * self.num_files_total)
				self.num_files_total = 0
				self.receiving_files = False

async def xbdm_emulator_server():
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

	print(f"XBDM emulator running on 0.0.0.0:{XBDM_PORT}!")
	asyncio.run(xbdm_emulator_server())

	return 0

if __name__ == "__main__":
	exit(main())