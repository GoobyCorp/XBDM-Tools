#!/usr/bin/python3

import asyncio
from io import BytesIO
from enum import IntEnum
from shutil import rmtree
from json import load, dump
from typing import BinaryIO
from struct import unpack, pack
from os import walk, rename, remove, makedirs
from os.path import isfile, isdir, join, getsize
from ctypes import Structure, Union, c_ulong, c_uint32, c_int32, c_uint64, c_int64

from xbdm_common import *

# constants
D3DFMT_A8R8G8B8 = 0x18280186
D3DFMT_A2R10G10B10 = 0x18280192

# ctypes aliases
c_dword = c_ulong

# config variables
CONFIG_FILE = "config.json"

# config
cfg: list | dict = {}

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
			if cfg["stock"]["debug"]:
				print(bytes(raw_command))
				print(raw_command.hex().upper())
			parsed = XBDMCommand.parse(raw_command)
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
					self.send_single_line("200- recoverytype=5 hresult=0x00000491")
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
					file_name = parsed.get_param("name")
					file_path = xbdm_to_device_path(file_name)
					if parsed.param_exists("remove") and parsed.get_param("remove"):  # deleting file
						print(f"Deleting file \"{file_name}\"...")
						if isfile(file_path):
							remove(file_path)
						self.send_single_line("200- OK")
					elif parsed.param_exists("removedir") and parsed.get_param("removedir"):  # deleting directory
						print(f"Deleting directory \"{file_name}\"...")
						if isdir(file_path):
							rmtree(file_path, True)
						self.send_single_line("200- OK")
					elif parsed.param_exists("size"):  # receiving file
						file_size = parsed.get_param("size")
						print(f"Receiving single file \"{file_name}\" (0x{file_size:X})...")
						print(f"0x{parsed.get_param('crc'):X}")
						self.send_single_line("204- send binary data")
						self.file_data_left = file_size
						self.file_cksm = parsed.get_param("crc")
						self.receiving_file = True
						self.receiving_type = ReceiveFileType.XBUPDATE_SINGLE
						self.file_path = file_path
					elif not parsed.param_exists("localsrc"):
						print(f"Modifying file \"{file_name}\"...")
						self.send_single_line("200- OK")
					elif parsed.param_exists("localsrc"):
						file_name_old = parsed.get_param("localsrc")
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
					self.send_single_line("200- " + cfg["stock"]["console_name"])
				case "consoletype":
					print("Sending console type...")
					self.send_single_line("200- " + cfg["stock"]["console_type"])
				case "consolefeatures":
					# Basic JRPC2 Support - Byrom
					if parsed.param_exists("ver") and parsed.param_exists("type"): # is jrpc2 command
						type_param = parsed.get_param("type")
						# type 0 to 8 are related to call function by the look of it
						#if type_param == "1": # example when loading a plugin
						#    print("JRPC2 - One of the call function commands received! Responding...")
						#    self.transport.write(b"200- 0\r\n") # 0 for load success
						if type_param == 9:
							print("JRPC2 - Resolve function command received! Responding...")
							self.send_single_line("200- 80067F48")
						elif type_param == 10:
							print("JRPC2 - Get CPUKey command received! Responding...")
							self.send_single_line("200- " + cfg["jrpc2"]["CPUKey"])
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
							self.send_single_line("200- " + cfg["jrpc2"]["KernelVers"])
						elif type_param == 14:
							print("JRPC2 - Set ROL LED command received! Responding...") # multple options for this green red orange topleft topright bottomleft bottomright
							self.send_single_line("200- S_OK")
						elif type_param == 15:
							gettemp_params = parsed.get_param("params")
							print(gettemp_params)
							if gettemp_params == "A\\0\\A\\1\\1\\0\\":
								print("JRPC2 - Get CPU Temperature command received! Responding...")
								self.send_single_line("200- " + hex(cfg["jrpc2"]["CPUTemp"]).replace("0x", ""))
							elif gettemp_params == "A\\0\\A\\1\\1\\1\\":
								print("JRPC2 - Get GPU Temperature command received! Responding...")
								self.send_single_line("200- " + hex(cfg["jrpc2"]["GPUTemp"]).replace("0x", ""))
							elif gettemp_params == "A\\0\\A\\1\\1\\2\\":
								print("JRPC2 - Get EDRAM Temperature command received! Responding...")
								self.send_single_line("200- " + hex(cfg["jrpc2"]["EDRAMTemp"]).replace("0x", ""))
							elif gettemp_params == "A\\0\\A\\1\\1\\3\\":
								print("JRPC2 - Get MOBO Temperature command received! Responding...")
								self.send_single_line("200- " + hex(cfg["jrpc2"]["MOBOTemp"]).replace("0x", ""))
						elif type_param == 16:
							print("JRPC2 - Get TitleID command received! Responding...")
							self.send_single_line("200- " + cfg["jrpc2"]["TitleID"])
						elif type_param == 17:
							print("JRPC2 - Get Mobo Type command received! Responding...")
							self.send_single_line("200- " + cfg["jrpc2"]["MoboType"])
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
							print("Feature Params: " + parsed.get_param("params"))
							self.send_single_line("200- S_OK")
						else:  #simple query
							self.send_single_line("200- " + cfg["stock"]["console_type"])
				case "advmem":
					if parsed.flag_exists("status"):
						print("Sending memory properties...")
						self.send_single_line("200- enabled")
				case "altaddr":
					print("Sending title IP address...")
					addr = bytes(map(int, cfg["stock"]["alternate_address"].split('.'))).hex()
					self.send_single_line("200- addr=0x" + addr)
				case "systime":
					print("Sending system time...")
					(time_low, time_high) = uint64_to_uint32(system_time())
					with XBDMCommand() as cmd:
						cmd.set_code(200)
						cmd.set_param("high", time_high, XBDMType.DWORD)
						cmd.set_param("low", time_low, XBDMType.DWORD)
						cmd_data = cmd.get_output(True)
					self.transport.write(cmd_data)
				case "systeminfo":
					print("Sending system info...")
					lines = [
						"HDD=" + "Enabled" if cfg["stock"]["hdd_enabled"] else "Disabled",
						"Type=" + cfg["stock"]["console_type"],
						f"Platform={cfg['stock']['platform']} System={cfg['stock']['system']}",
						f"BaseKrnl={cfg['stock']['base_kernel']} Krnl={cfg['stock']['kernel']} XDK={cfg['stock']['xdk']}"
					]
					self.send_multi_line(lines)
				case "xbeinfo":
					if parsed.flag_exists("RUNNING"):
						print("Sending current title info...")
						lines = [
							"timestamp=0x00000000 checksum=0x00000000",
							f"name=\"{cfg['stock']['current_title_path']}\""
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

					with open(cfg["stock"]["screenshot_file"], "rb") as f:
						# read and send the file
						data = f.read()

					with XBDMCommand() as cmd:
						cmd.set_param("pitch", p, XBDMType.DWORD)
						cmd.set_param("width", ow, XBDMType.DWORD)
						cmd.set_param("height", oh, XBDMType.DWORD)
						cmd.set_param("format", D3DFMT_A8R8G8B8, XBDMType.DWORD)
						cmd.set_param("offsetx", 0, XBDMType.DWORD)
						cmd.set_param("offsety", 0, XBDMType.DWORD)
						cmd.set_param("framebuffersize", len(data), XBDMType.DWORD)  # 0x398000
						cmd.set_param("sw", sw, XBDMType.DWORD)
						cmd.set_param("sh", sh, XBDMType.DWORD)
						cmd.set_param("colorspace", 0, XBDMType.DWORD)
						self.transport.write(cmd.get_output(True, True))
					self.transport.write(data)
				case "drivelist":
					print("Sending drive list...")
					self.send_multi_line([f"drivename=\"{x}\"" for x in list_drives()])
				case "isdebugger":
					print("Requesting is debugger...")
					self.send_single_line("410- name=\"XRPC\" user=" + cfg["stock"]["username"])
				case "break":
					if parsed.flag_exists("clearall"):
						print("Removing all breakpoints...")
						self.send_single_line("200- OK")
				case "modules":
					print("Sending module listing...")
					lines = []
					for single in cfg["stock"]["modules"]:
						with XBDMCommand() as cmd:
							cmd.set_param("name", single["name"], XBDMType.QUOTED_STRING)
							cmd.set_param("base", single["base"], XBDMType.DWORD)
							cmd.set_param("size", single["size"], XBDMType.DWORD)
							cmd.set_param("check", 0, XBDMType.DWORD)
							cmd.set_param("timestamp", 0, XBDMType.DWORD)
							cmd.set_param("pdata", 0, XBDMType.DWORD)
							cmd.set_param("psize", 0, XBDMType.DWORD)
							cmd.set_param("thread", 0, XBDMType.DWORD)
							cmd.set_param("osize", 0, XBDMType.DWORD)
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
						(low, high) = uint64_to_uint32(cfg["stock"]["console_hdd_size"], True, True)
						with XBDMCommand() as cmd:
							cmd.set_param("freetocallerlo", low, XBDMType.DWORD)
							cmd.set_param("freetocallerhi", high, XBDMType.DWORD)
							cmd.set_param("totalbyteslo", low, XBDMType.DWORD)
							cmd.set_param("totalbyteshi", high, XBDMType.DWORD)
							cmd.set_param("totalfreebyteslo", low, XBDMType.DWORD)
							cmd.set_param("totalfreebyteshi", high, XBDMType.DWORD)
							cmd_data = cmd.get_output(True)
						self.send_multi_line([cmd_data])
				case "dirlist":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME"))
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
									cmd.set_param("name", single, XBDMType.QUOTED_STRING)
									cmd.set_param("sizehi", size_high, XBDMType.DWORD)
									cmd.set_param("sizelo", size_low, XBDMType.DWORD)
									cmd.set_param("createhi", ctime_high, XBDMType.DWORD)
									cmd.set_param("createlo", ctime_low, XBDMType.DWORD)
									cmd.set_param("changehi", mtime_high, XBDMType.DWORD)
									cmd.set_param("changelo", mtime_low, XBDMType.DWORD)
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
						phys_path = xbdm_to_local_path(parsed.get_param("NAME"))
						print(f"Requesting file attributes for \"{phys_path}\"...")
						if isfile(phys_path):
							print("File exists...")
							file_size = getsize(phys_path)
							(ctime_low, ctime_high) = uint64_to_uint32(creation_time_to_file_time(phys_path), True)
							(mtime_low, mtime_high) = uint64_to_uint32(modify_time_to_file_time(phys_path), True)
							(size_low, size_high) = uint64_to_uint32(file_size, True)
							with XBDMCommand() as cmd:
								cmd.set_param("sizehi", size_high, XBDMType.DWORD)
								cmd.set_param("sizelo", size_low, XBDMType.DWORD)
								cmd.set_param("createhi", ctime_high, XBDMType.DWORD)
								cmd.set_param("createlo", ctime_low, XBDMType.DWORD)
								cmd.set_param("changehi", mtime_high, XBDMType.DWORD)
								cmd.set_param("changelo", mtime_low, XBDMType.DWORD)
								cmd_data = cmd.get_output(True)
							self.send_multi_line([cmd_data])
						else:
							print("File doesn't exist...")
							self.send_single_line("402- file not found")
				case "mkdir":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME"))
						if not isfile(phys_path) and not isdir(phys_path):
							print(f"Created directory \"{phys_path}\"...")
							makedirs(phys_path, exist_ok=True)
							self.send_single_line("200- OK")
				case "getfile":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME"))
						if isfile(phys_path):
							print(f"Sending file @ \"{phys_path}\"...")
							with open(phys_path, "rb") as f:
								data = f.read()
							self.send_single_line("203- binary response follows")
							self.transport.write(pack("<I", len(data)))
							self.transport.write(data)
				case "sendvfile":
					if parsed.param_exists("COUNT"):
						file_count = parsed.get_param("COUNT")
						print(f"Receiving {file_count} file(s)...")
						if file_count > 0:
							self.send_single_line("204- send binary data")
							self.num_files_total = file_count
							self.num_files_left = file_count
							self.receiving_files = True
							self.send_single_line("203- binary response follows")
							self.transport.write((b"\x00" * 4) * self.num_files_total)
				case "sendfile":
					file_name = parsed.get_param("NAME")
					file_size = parsed.get_param("LENGTH")
					print(f"Receiving single file \"{file_name}\" (0x{file_size:X})...")
					self.send_single_line("204- send binary data")
					self.file_data_left = file_size
					self.receiving_file = True
					self.receiving_type = ReceiveFileType.SENDFILE_SINGLE
					self.file_path = xbdm_to_device_path(file_name)
				case "rename":
					if parsed.param_exists("NAME") and parsed.param_exists("NEWNAME"):
						old_file_path = xbdm_to_local_path(parsed.get_param("NAME"))
						new_file_path = xbdm_to_local_path(parsed.get_param("NEWNAME"))
						if isfile(old_file_path) or isdir(old_file_path):
							print(f"Renaming \"{old_file_path}\" to \"{new_file_path}\"...")
							rename(old_file_path, new_file_path)
							self.send_single_line("200- OK")
				case "delete":
					if parsed.param_exists("NAME"):
						phys_path = xbdm_to_local_path(parsed.get_param("NAME"))
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
						setmem_data = parsed.get_param("data")
						print(f"Attempted to set {len(setmem_data)} byte(s) @ {setmem_addr}...")
						self.send_single_line(f"200- set {str(len(setmem_data))} bytes")
				case "getmem" | "getmemex":
					if parsed.param_exists("ADDR") and parsed.param_exists("LENGTH"):
						addr = parsed.get_param("ADDR")
						length = parsed.get_param("LENGTH")
						# length = unpack("!I", bytes.fromhex(length.replace("0x", "")))[0]
						print(f"Attempted to get {length} byte(s) @ {addr}...")
						self.send_single_line("203- binary response follows")
						self.transport.write(pack("<H", 1024) + (b"suckcock" * 128))
						self.transport.write(pack("<H", 1024) + (b"suckcock" * 128))
						self.transport.write(pack("<H", 1024) + (b"suckcock" * 128))
						self.transport.write(pack("<H", 1024) + (b"suckcock" * 128))
				case "setsystime":
					if parsed.param_exists("clocklo") and parsed.param_exists("clockhi") and parsed.param_exists("tz"):
						sys_time_low = parsed.get_param("clocklo")
						sys_time_high = parsed.get_param("clockhi")
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
	global cfg

	if isfile(CONFIG_FILE):
		cfg = load(open(CONFIG_FILE, "r"))
	else:
		cfg = {
			"stock": {
				"xbdm_dir": "XBDM"
			},
			"jrpc2": {
				"MoboType": "Trinity",
				"CPUKey": "13371337133713371337133713371337",
				"KernelVers": "17559",
				"TitleID": "FFFE07D1",
				"CPUTemp": 45,
				"GPUTemp": 44,
				"EDRAMTemp": 43,
				"MOBOTemp": 39
			}
		}
		dump(cfg, open(CONFIG_FILE, "w"))

	print(f"XBDM emulator running on 0.0.0.0:{XBDM_PORT}!")
	asyncio.run(xbdm_emulator_server())

	return 0

if __name__ == "__main__":
	exit(main())