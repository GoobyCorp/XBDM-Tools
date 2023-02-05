#!/usr/bin/env python3

import re
import asyncio
from json import loads
from typing import Any
from shlex import shlex
from pathlib import Path
from enum import IntEnum
from calendar import timegm
from struct import pack, unpack
from argparse import ArgumentParser
from datetime import datetime, timedelta, tzinfo

# xbdm variables
XBDM_PORT = 730
XBDM_BUFF_SIZE = 1460
XBDM_DIR = "DEVICES"
XBDM_NEWLINE = b"\r\n"

# constants
MANIFEST_FILE = "recovery_manifest_21256_18.json"

# time variables
EPOCH_AS_FILETIME = 116444736000000000
HUNDREDS_OF_NANOSECONDS = 10000000
ZERO = timedelta(0)
HOUR = timedelta(hours=1)

# variables
MANIFEST: None | dict = None

# arguments
XBDM_HOST: str = ""
SHADOWBOOT_PATH: str = ""

# regex
CODE_EXP = re.compile(r"^(\d+)-")

def format_response(command: bytes | bytearray, lowercase: bool = False):
	command =  command.decode("UTF8").rstrip()
	if lowercase:
		command = command.lower()
	return command

def read_manifest() -> dict:
	return loads(Path(MANIFEST_FILE).read_text())

def xbdm_to_device_path(path: str) -> str:
	if path.startswith("\\Device\\"):
		path = path[len("\\Device\\"):]
	elif path.startswith("\\"):
		path = path[1:]

	p = Path(XBDM_DIR)
	p /= path.replace(":\\", "/").replace("\\", "/")
	p = p.absolute()
	# p.parent.mkdir(parents=True, exist_ok=True)
	return str(p)

def dt_to_filetime(dt):
	if (dt.tzinfo is None) or (dt.tzinfo.utcoffset(dt) is None):
		dt = dt.replace(tzinfo=UTC())
	ft = EPOCH_AS_FILETIME + (timegm(dt.timetuple()) * HUNDREDS_OF_NANOSECONDS)
	return ft + (dt.microsecond * 10)

def creation_time_to_file_time(path: str) -> int:
	#dt = datetime.utcfromtimestamp(getctime(path))
	return dt_to_filetime(datetime.utcnow())

def uint64_to_uint32(num: int, as_hex: bool = False, as_bytes: bool = False) -> tuple | list:
	i = unpack("<II", pack("<Q", num))
	if as_hex:
		low = "0x" + pack("!I", i[0]).hex()
		high = "0x" + pack("!I", i[1]).hex()
		if as_bytes:
			return [bytes(low, "utf8"), bytes(high, "utf8")]
		return [low, high]
	return i

class UTC(tzinfo):
	def utcoffset(self, dt):
		return ZERO

	def tzname(self, dt):
		return "UTC"

	def dst(self, dt):
		return ZERO

class XBDMResponseStatus(IntEnum):
	OK = 200
	MULTILINE = 202
	BINARY = 203
	SENDBINARYDATA = 204
	ERROR = 405

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

class CRC32:
	iv: int = 0
	poly: int = 0
	value: int = 0
	table: list = []

	def __init__(self, iv: int, poly: int):
		self.reset()
		self.iv = iv
		self.poly = poly

		self.compute_table()

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		pass

	def reset(self) -> None:
		self.iv = 0
		self.poly = 0
		self.value = 0
		self.table = []

	def compute_table(self) -> None:
		for byt in range(256):
			crc = 0
			for bit in range(8):
				if (byt ^ crc) & 1:
					crc = (crc >> 1) ^ self.poly
				else:
					crc >>= 1
				byt >>= 1
			self.table.append(crc & 0xFFFFFFFF)

	def process(self, data: bytes | bytearray) -> int:
		if self.value == 0:
			self.value = self.iv
		for b in data:
			self.value = self.table[(b ^ self.value) & 0xFF] ^ (self.value >> 8)
		return self.value & 0xFFFFFFFF

async def open_xbdm_connection() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
	(reader, writer) = await asyncio.open_connection(XBDM_HOST, XBDM_PORT)

	# receive 201- connected
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt0 = XBDMCommand.parse(format_response(data))

	assert pkt0.code == 201

	return (reader, writer)

async def close_xbdm_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
	# send bye
	writer.write(b"BYE" + XBDM_NEWLINE)
	await writer.drain()

	# receive 200- bye
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt2 = XBDMCommand.parse(format_response(data))

	assert pkt2.code == 200

	writer.close()

async def send_xbdm_command(cmd: XBDMCommand) -> XBDMCommand:
	(reader, writer) = await open_xbdm_connection()

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt1 = XBDMCommand.parse(format_response(data))

	if cmd.name in ["recovery", "magicboot"]:
		writer.close()
	else:
		await close_xbdm_connection(reader, writer)

	# return response packet
	return pkt1

async def send_xbdm_upload_file(local_path: str, remote_path: str) -> None:
	p = Path(local_path)

	assert p.exists() and p.is_file()

	(reader, writer) = await open_xbdm_connection()

	fs = p.stat().st_size
	with p.open("rb") as f:
		cmd = XBDMCommand()
		cmd.set_name("SENDFILE")
		cmd.set_param("NAME", remote_path, True)
		cmd.set_param("LENGTH", fs)

		print(cmd.get_output(False, False))

		# send command
		writer.write(cmd.get_output(True))
		await writer.drain()

		# receive response
		data = await reader.readuntil(XBDM_NEWLINE)
		pkt1 = XBDMCommand.parse(format_response(data))

		assert pkt1.code == 204

		# send file data
		while True:
			data = f.read(XBDM_BUFF_SIZE)
			if not data:
				break
			writer.write(data)
			await writer.drain()

	# receive response
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt2 = XBDMCommand.parse(format_response(data))

	assert pkt2.code == 200

	await close_xbdm_connection(reader, writer)

async def send_xbupd_upload_file(local_path: str, remote_path: str) -> None:
	p = Path(local_path)

	assert p.exists() and p.is_file()

	(reader, writer) = await open_xbdm_connection()

	(ctime_low, ctime_high) = uint64_to_uint32(creation_time_to_file_time(str(p)), True)

	fs = p.stat().st_size
	with p.open("rb") as f:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!sysfileupd")
		cmd.set_param("name", remote_path, True)
		cmd.set_param("size", fs)
		cmd.set_param("ftimelo", ctime_low)
		cmd.set_param("ftimehi", ctime_high)

		if remote_path.count("\\") == 1:  # root path
			cmd.set_flag("bootstrap")

		with CRC32(0xFFFFFFFF, 0xEDB88320) as c:
			while True:
				data = f.read(XBDM_BUFF_SIZE)
				if not data:
					break
				c.process(data)
			cmd.set_param("crc", c.value)

		f.seek(0)

		print(cmd.get_output(False, False))

		# send command
		writer.write(cmd.get_output(True))
		await writer.drain()

		# receive response
		data = await reader.readuntil(XBDM_NEWLINE)
		pkt1 = XBDMCommand.parse(format_response(data))

		assert pkt1.code == 204

		# send file data
		while True:
			data = f.read(XBDM_BUFF_SIZE)
			if not data:
				break
			writer.write(data)
			await writer.drain()

	# receive response
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt2 = XBDMCommand.parse(format_response(data))

	assert pkt2.code == 200

	await close_xbdm_connection(reader, writer)

async def send_xbupd_delete_file(remote_path: str) -> XBDMCommand:
	(reader, writer) = await open_xbdm_connection()

	# create command
	cmd = XBDMCommand()
	cmd.set_name("xbupdate!sysfileupd")
	cmd.set_param("name", remote_path, True)
	cmd.set_param("remove", "1")

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt1 = XBDMCommand.parse(format_response(data))

	assert pkt1.code == 200

	await close_xbdm_connection(reader, writer)

	# return response packet
	return pkt1

async def send_xbupd_delete_dir(remote_path: str) -> XBDMCommand:
	(reader, writer) = await open_xbdm_connection()

	# create command
	cmd = XBDMCommand()
	cmd.set_name("xbupdate!sysfileupd")
	cmd.set_param("name", remote_path, True)
	cmd.set_param("removedir", "1")

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt1 = XBDMCommand.parse(format_response(data))

	assert pkt1.code == 200

	await close_xbdm_connection(reader, writer)

	# return response packet
	return pkt1

async def send_xbupd_rename_file(remote_path_old: str, remote_path_new: str) -> XBDMCommand:
	(reader, writer) = await open_xbdm_connection()

	# create command
	cmd = XBDMCommand()
	cmd.set_name("xbupdate!sysfileupd")
	cmd.set_param("name", remote_path_new, True)
	cmd.set_param("localsrc", remote_path_old, True)

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt1 = XBDMCommand.parse(format_response(data))

	assert pkt1.code == 200

	await close_xbdm_connection(reader, writer)

	# return response packet
	return pkt1

async def xbdm_recovery_client():
	# send latest xbupdate.xex to the console
	await send_xbdm_upload_file(xbdm_to_device_path("\\Device\\Flash\\xbupdate.xex"), "\\Device\\Flash\\xbupdate.xex")

	cmd = XBDMCommand()
	cmd.set_name("recovery")
	await send_xbdm_command(cmd)

	print("Waiting 30 seconds for recovery to boot...")
	await asyncio.sleep(30)

	cmd.reset()
	cmd.set_name("xbupdate!drawtext")
	cmd.set_param("text", "UwU", True)
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!version")
	cmd.set_param("verhi", 0x20000)
	cmd.set_param("verlo", 0x53080012)
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.set_name("xbupdate!validdevice")
	cmd.set_param("basesysver", "1888")
	cmd.set_param("mbneeded", "210")
	print(cmd.get_output(False, False))
	rep = await send_xbdm_command(cmd)
	print(rep.get_output(False, False))

	valid = rep.get_param("valid").as_bool()
	devidx = rep.get_param("deviceindex").as_int()

	assert valid, "No valid device found to write recovery to!"

	cmd.reset()
	cmd.set_name("xbupdate!validatehddpartitions")
	print(cmd.get_output(False, False))
	rep = await send_xbdm_command(cmd)
	print(rep.get_output(False, False))

	valid = rep.get_param("valid").as_bool()

	assert valid, "No valid device found to write recovery to!"

	cmd.reset()
	cmd.set_name("xbupdate!isflashclean")
	print(cmd.get_output(False, False))
	rep = await send_xbdm_command(cmd)
	print(rep.get_output(False, False))

	valid = rep.flag_exists("TRUE")

	assert valid, "Flash isn't clean!"

	cmd.reset()
	cmd.set_name("xbupdate!instrecoverytype")
	print(cmd.get_output(False, False))
	rep = await send_xbdm_command(cmd)
	print(rep.get_output(False, False))

	rectyp = rep.get_param("recoverytype").as_int()
	hres = rep.get_param("hresult").as_int()

	assert rectyp, "Invalid recovery type!"

	cmd.reset()
	cmd.set_name("xbupdate!version")
	cmd.set_param("verhi", 0x20000)
	cmd.set_param("verlo", 0x53080012)
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!configure")
	cmd.set_param("flashstart", 0x200000)
	cmd.set_flag("ffs")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!recovery")
	cmd.set_param("installver", "17489")
	cmd.set_param("selectedver", "17489")
	cmd.set_param("autoupd", "0")
	cmd.set_param("rectype", "1")
	cmd.set_param("deviceindex", str(devidx))
	cmd.set_flag("noformathdd")
	cmd.set_flag("formatulrcache")
	cmd.set_flag("formatsysext")
	cmd.set_flag("createsysextrd")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	# delete files
	for remote_path in MANIFEST["upd_files_to_delete"]:
		await send_xbupd_delete_file(remote_path)

	# delete directories
	for remote_path in MANIFEST["upd_dirs_to_delete"]:
		await send_xbupd_delete_dir(remote_path)

	# upload files
	# shadowboot
	await  send_xbupd_upload_file(SHADOWBOOT_PATH, "\\Device\\Harddisk0\\Partition1\\xboxrom_update.bin")
	# system files
	for remote_path in MANIFEST["upd_files_to_upload_default"]:
		await send_xbupd_upload_file(xbdm_to_device_path(remote_path), remote_path)
	# aux and ext
	#for remote_path in MANIFEST["upd_files_to_upload_samples"]:
	#	await send_xbupd_upload_file(xbdm_to_device_path(remote_path), remote_path)
	# samples
	#for remote_path in MANIFEST["upd_files_to_upload_aux_ext"]:
	#	await send_xbupd_upload_file(xbdm_to_device_path(remote_path), remote_path)

	# rename files
	#for (remote_path_old, remote_path_new) in UPD_FILES_TO_RENAME:
	#	await send_xbupd_rename_file(remote_path_old, remote_path_new)

	# all the other commands
	cmd.reset()
	cmd.set_name("xbupdate!close")
	cmd.set_flag("final")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!flash")
	cmd.set_param("romdir", "\\Device\\Harddisk0\\Partition3\\ROM", True)
	cmd.set_flag("enum")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!flash")
	cmd.set_param("romdir", "\\Device\\Harddisk0\\Partition3\\ROM\\0000", True)
	cmd.set_flag("query")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!commitsysextramdisk")
	cmd.set_param("deviceindex", str(devidx))
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!getregion")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.reset()
	cmd.set_name("xbupdate!setxamfeaturemask")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.set_name("xbupdate!finish")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.set_name("xbupdate!restart")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

	cmd.set_name("magicboot")
	cmd.set_flag("cold")
	print(cmd.get_output(False, False))
	await send_xbdm_command(cmd)

def main() -> int:
	global XBDM_HOST, SHADOWBOOT_PATH, MANIFEST

	parser = ArgumentParser(description="A script to recover Xbox 360 devkits")
	parser.add_argument("host", type=str, help="The devkit IP address")
	parser.add_argument("image", type=str, help="The shadowboot image to install to flash")
	args = parser.parse_args()

	XBDM_HOST = args.host
	SHADOWBOOT_PATH = args.image

	assert Path(SHADOWBOOT_PATH).is_file(), "Shadowboot image doesn't exist!"

	MANIFEST = read_manifest()

	asyncio.run(xbdm_recovery_client())

	return 0

if __name__ == "__main__":
	exit(main())