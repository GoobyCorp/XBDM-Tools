import re
import asyncio
from io import BytesIO
from shlex import shlex
from enum import IntEnum
from pathlib import Path
from calendar import timegm
from shutil import copyfileobj
from struct import pack, unpack
from typing import Any, BinaryIO
from datetime import datetime, timedelta, tzinfo

# pip install nest-asyncio
import nest_asyncio

# xbdm variables
XBDM_PORT = 730
XBDM_BUFF_SIZE = 1460
XBDM_NEWLINE = b"\r\n"
XBDM_BYE = b"BYE" + XBDM_NEWLINE
XBDM_CONNECTED = b"201- connected" + XBDM_NEWLINE

# time variables
EPOCH_AS_FILETIME = 116444736000000000
HUNDREDS_OF_NANOSECONDS = 10000000
ZERO = timedelta(0)
HOUR = timedelta(hours=1)

# regex
CODE_EXP = re.compile(r"^(\d+)-")

# constants
MASK_UINT8 = 0xFF
MASK_UINT16 = 0xFFFF
MASK_UINT32 = 0xFFFFFFFF
MASK_UINT64 = 0xFFFFFFFFFFFFFFFF

def dt_to_filetime(dt):
	if (dt.tzinfo is None) or (dt.tzinfo.utcoffset(dt) is None):
		dt = dt.replace(tzinfo=UTC())
	ft = EPOCH_AS_FILETIME + (timegm(dt.timetuple()) * HUNDREDS_OF_NANOSECONDS)
	return ft + (dt.microsecond * 10)

def creation_time_to_file_time(path: str) -> int:
	return dt_to_filetime(datetime.utcnow())

def uint64_to_uint32(num: int, as_hex: bool = False, as_bytes: bool = False) -> tuple[int, int] | tuple[bytes, bytes] | tuple[str, str]:
	i = unpack("<II", pack("<Q", num))
	if as_hex:
		low = "0x" + pack("!I", i[0]).hex()
		high = "0x" + pack("!I", i[1]).hex()
		if as_bytes:
			return (bytes(low, "utf8"), bytes(high, "utf8"))
		return (low, high)
	return i

class UTC(tzinfo):
	def utcoffset(self, dt):
		return ZERO

	def tzname(self, dt):
		return "UTC"

	def dst(self, dt):
		return ZERO

def connect_before(func):
	def wrapper(*args, **kwargs):
		self = args[0]
		if isinstance(self, (BaseXBDMClient, XBUpdateXBDMClient, RGLoaderXBDMClient)):
			self.connect_and_check()
			res = func(*args, **kwargs)
			return res
	return wrapper

def disconnect_after(func):
	def wrapper(*args, **kwargs):
		self = args[0]
		if isinstance(self, (BaseXBDMClient, XBUpdateXBDMClient, RGLoaderXBDMClient)):
			res = func(*args, **kwargs)
			self.send_bye()
			self.disconnect()
			return res
	return wrapper

def expect_ok(func):
	def wrapper(*args, **kwargs):
		self = args[0]
		if isinstance(self, (BaseXBDMClient, XBUpdateXBDMClient, RGLoaderXBDMClient)):
			res = func(*args, **kwargs)
			self.expect_code(XBDMCode.OK)
			return res
	return wrapper

class XBDMCode(IntEnum):
	OK = 200
	CONNECTED = 201
	MULTILINE = 202
	BINARY_RESPONSE_FOLLOWS = 203
	SEND_BINARY_DATA = 204
	ERROR = 405
	ERROR_PATH_NOT_FOUND = 430

class XBDMType(IntEnum):
	NONE = 0
	DWORD = 1
	QWORD = 2
	BYTES = 3
	STRING = 4
	QUOTED_STRING = 5
	BOOL = 6

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

	# used as a shortcut for buffered copies
	write = process

class XBDMShlex(shlex):
	def __init__(self, *args, **kwargs):
		kwargs["posix"] = True
		super(XBDMShlex, self).__init__(*args, **kwargs)
		self.escape = ""  #remove the \ escape
		self.whitespace_split = True

class XBDMCommand:
	name = None
	code = 0
	args = dict[str, tuple[Any, XBDMType]]
	flags = list[str]
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

	def enforce_types(self, value: Any, t: XBDMType) -> None:
		if t == XBDMType.DWORD:
			assert isinstance(value, int)
		elif t == XBDMType.QWORD:
			assert isinstance(value, int)
		elif t == XBDMType.QUOTED_STRING:
			assert isinstance(value, str)
		elif t == XBDMType.BOOL:
			assert isinstance(value, int) or isinstance(value, bool)
			assert value in [0, 1] or isinstance(value, bool)
		elif t == XBDMType.STRING:
			assert isinstance(value, str)

	def value_to_type(self, value: str) -> XBDMType:
		if value.startswith("0x"):
			t = XBDMType.DWORD
		elif value.startswith("0q"):
			t = XBDMType.QWORD
		elif value.startswith('"') or value.startswith("'"):
			t = XBDMType.QUOTED_STRING
		elif value.lower() in ["true", "false"]:
			t = XBDMType.BOOL
		else:
			try:
				v = int(value)
				if v == 0 or v == 1:
					t = XBDMType.BOOL
				else:
					t = XBDMType.DWORD
			except:
				t = XBDMType.STRING
		return t

	def value_to_output(self, value: Any, t: XBDMType) -> str:
		if t == XBDMType.DWORD:
			value = "0x" + value.to_bytes(4, "big").hex().upper()
		elif t == XBDMType.QWORD:
			value = "0q" + value.to_bytes(8, "big").hex().upper()
		elif t == XBDMType.QUOTED_STRING:
			value = f'"{value}"'
		elif t == XBDMType.BOOL:
			value = "1" if value else "0"
		return value

	def value_apply_type(self, value: str, t: XBDMType) -> Any:
		if t == XBDMType.DWORD:
			if value.startswith("0x"):
				value = int(value, 16)
			else:
				value = int(value)
		elif t == XBDMType.QWORD:
			if value.startswith("0x") or value.startswith("0q"):
				value = int(value.replace("0q", "0x"), 16)
			else:
				value = int(value)
		elif t == XBDMType.QUOTED_STRING:
			pass
		elif t == XBDMType.BOOL:
			value = value.lower()
			if value == "true" or value == "1":
				value = True
			elif value == "false" or value == "0":
				value = False
		return value

	@staticmethod
	def parse(command: str):
		cmd = XBDMCommand()
		sh = XBDMShlex(command)
		command = list(sh)
		match = CODE_EXP.match(command[0])
		if match:  # response
			cmd.set_code(int(match.group(1)))
		else:  # command
			cmd.set_name(command[0])

		if len(command) > 1:
			for single in command[1:]:
				if "=" in single:
					(key, value) = single.split("=", 1)
					t = cmd.value_to_type(value)
					v = cmd.value_apply_type(value, t)
					cmd.set_param(key, v, t)
				else:
					if not cmd.flag_exists(single):
						cmd.set_flag(single)
		return cmd

	def set_name(self, name: str) -> None:
		self.name = name

	def set_code(self, code: int) -> None:
		self.code = code

	def get_code(self) -> int:
		return self.code

	def get_flags(self) -> list[str]:
		return self.flags

	def flag_exists(self, key: str) -> bool:
		return key.lower() in self.flags

	def param_exists(self, key: str, lc_check: bool = False) -> bool:
		return self.get_param(key, lc_check) is not None

	def set_flag(self, key: str) -> Any:
		return self.flags.append(key.lower())

	def set_param(self, key: str, value: Any, t: XBDMType) -> None:
		key = key.lower()
		self.enforce_types(value, t)
		self.args[key] = (value, t)

	def get_params(self) -> dict:
		return self.args

	def get_param(self, key: str, lc_check: bool = False) -> Any | None:
		print(self.args)
		val = self.args.get(key)
		if lc_check and val is None:
			val = self.args.get(key.lower())
		if val is None:
			return None
		(v, t) = val
		return v

	def get_output(self, as_bytes: bool = False, line_ending: bool = True) -> str | bytes:
		o = ""
		if self.name is not None:  # commands only
			o = self.name
		if self.code is not None and self.code != 0:  # replies only
			o = str(self.code) + "-"
		if len(self.args) > 0:
			o += " "
			o += " ".join([f"{k}={self.value_to_output(v, t)}" for (k, (v, t)) in self.args.items()])
		if len(self.flags) > 0:
			o += " "
			o += " ".join(self.flags)
		if line_ending:
			o += "\r\n"
		if as_bytes:
			return o.encode("UTF8")
		# self.reset()
		return o

class AsyncXBDMClient:
	addr: str = None
	reader: asyncio.StreamReader = None
	writer: asyncio.StreamWriter = None

	def __init__(self, addr: str):
		self.reset()

		self.addr = addr

	async def __aenter__(self):
		return self

	async def __aexit__(self, *args, **kwargs):
		pass

	def reset(self) -> None:
		self.addr = None
		self.reader = None
		self.writer = None

	async def connect(self) -> None:
		(self.reader, self.writer) = await asyncio.open_connection(self.addr, XBDM_PORT)

	async def disconnect(self) -> None:
		if self.writer is not None:
			self.writer.close()

	async def readline(self) -> bytes:
		return await self.reader.readuntil(XBDM_NEWLINE)

	async def read(self, size: int) -> bytes:
		bl = size
		with BytesIO() as bio:
			while bl > 0:
				if bl < XBDM_BUFF_SIZE:
					tmp = await self.reader.read(bl)
				else:
					tmp = await self.reader.read(XBDM_BUFF_SIZE)
				if not tmp:
					break
				bio.write(tmp)
				return bio.getvalue()

	async def write(self, data: bytes | bytearray) -> None:
		with BytesIO(data) as bio:
			copyfileobj(bio, self.writer, XBDM_BUFF_SIZE)
		await self.writer.drain()

class BaseXBDMClient:
	reader: asyncio.ReadTransport = None
	writer: asyncio.WriteTransport = None
	loop: asyncio.AbstractEventLoop = None
	axc: AsyncXBDMClient = None

	def __init__(self, addr: str):
		self.reset()

		self.loop = asyncio.get_event_loop()
		nest_asyncio.apply(self.loop)
		self.axc = AsyncXBDMClient(addr)

	def __enter__(self):
		return self

	def __exit__(self, exc_type, exc_val, exc_tb):
		self.close()

	def reset(self) -> None:
		self.reader = None
		self.writer = None
		self.loop = None
		self.axc = None

	def connect(self) -> None:
		self.loop.run_until_complete(self.__async__connect())

	async def __async__connect(self) -> None:
		async with self.axc as cli:
			return await cli.connect()

	def connect_and_check(self) -> None:
		self.connect()
		self.expect_code(XBDMCode.CONNECTED)

	def disconnect(self) -> None:
		self.loop.run_until_complete(self.__async__disconnect())

	async def __async__disconnect(self) -> None:
		async with self.axc as cli:
			await cli.disconnect()

	def close(self) -> None:
		self.disconnect()
		self.loop.close()

	def readline(self) -> bytes:
		return self.loop.run_until_complete(self.__async__readline())

	async def __async__readline(self) -> bytes:
		async with self.axc as cli:
			return await cli.readline()

	def read(self, size: int) -> bytes:
		return self.loop.run_until_complete(self.__async__read(size))

	async def __async__read(self, size: int) -> bytes:
		async with self.axc as cli:
			return await cli.read(size)

	def write(self, data: bytes | bytearray) -> None:
		self.loop.run_until_complete(self.__async__write(data))

	async def __async__write(self, data: bytes | bytearray) -> None:
		async with self.axc as cli:
			await cli.write(data)

	def writefileobj(self, src: BinaryIO) -> None:
		copyfileobj(src, self, XBDM_BUFF_SIZE)

	def readfileobj(self, dst: BinaryIO) -> None:
		copyfileobj(self, dst, XBDM_BUFF_SIZE)

	def send_command(self, cmd: XBDMCommand) -> None:
		self.write(cmd.get_output(True))

	def send_bye(self) -> None:
		self.write(XBDM_BYE)

	def receive_reply(self) -> XBDMCommand:
		return XBDMCommand.parse(self.readline().decode("ASCII"))

	def expect_code(self, code: XBDMCode | int) -> None:
		rep = XBDMCommand.parse(self.readline().decode("ASCII"))
		assert rep.code == code, f"Expected {code}, got {rep.code}"

	def expect_codes(self, codes: list[XBDMCode]) -> None:
		rep = XBDMCommand.parse(self.readline().decode("ASCII"))
		assert rep.code in codes, f"{rep.code} not in {', '.join([str(x.value) for x in codes])}"

	@connect_before
	def recovery(self) -> None:
		cmd = XBDMCommand()
		cmd.set_name("recovery")

		self.send_command(cmd)

	@connect_before
	@expect_ok
	@disconnect_after
	def upload_file(self, local_path: str, remote_path: str) -> None:
		lp = Path(local_path)
		# rp = Path(remote_path)

		assert lp.exists() and lp.is_file(), "Local file doesn't exist!"

		ls = lp.stat().st_size
		with lp.open("rb") as lf:
			cmd = XBDMCommand()
			cmd.set_name("SENDFILE")
			cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)
			cmd.set_param("LENGTH", ls, XBDMType.DWORD)

			self.send_command(cmd)
			self.expect_code(XBDMCode.SEND_BINARY_DATA)
			self.writefileobj(lf)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	def magic_boot(self, flag: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("magicboot")
		cmd.set_flag(flag)

		self.send_command(cmd)

class XBUpdateXBDMClient(BaseXBDMClient):
	@connect_before
	@expect_ok
	@disconnect_after
	def upload_file(self, local_path: str, remote_path: str) -> None:
		lp = Path(local_path)
		# rp = Path(remote_path)

		assert lp.exists() and lp.is_file(), "Local file doesn't exist!"

		(ctime_low, ctime_high) = uint64_to_uint32(creation_time_to_file_time(str(lp)))

		ls = lp.stat().st_size
		with lp.open("rb") as lf:
			cmd = XBDMCommand()
			cmd.set_name("xbupdate!sysfileupd")
			cmd.set_param("name", remote_path, XBDMType.QUOTED_STRING)
			cmd.set_param("size", ls, XBDMType.DWORD)
			cmd.set_param("ftimelo", ctime_low, XBDMType.DWORD)
			cmd.set_param("ftimehi", ctime_high, XBDMType.DWORD)

			if remote_path.count("\\") == 1:
				cmd.set_flag("bootstrap")

			with CRC32(0xFFFFFFFF, 0xEDB88320) as c:
				copyfileobj(lf, c, XBDM_BUFF_SIZE)
				cmd.set_param("crc", c.value, XBDMType.DWORD)

			lf.seek(0)

			self.send_command(cmd)
			self.expect_code(XBDMCode.SEND_BINARY_DATA)
			self.writefileobj(lf)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@expect_ok
	@disconnect_after
	def delete_file(self, remote_path: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!sysfileupd")
		cmd.set_param("name", remote_path, XBDMType.QUOTED_STRING)
		cmd.set_param("remove", "1", XBDMType.BOOL)

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@expect_ok
	@disconnect_after
	def delete_dir(self, remote_path: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!sysfileupd")
		cmd.set_param("name", remote_path, XBDMType.QUOTED_STRING)
		cmd.set_param("removedir", "1", XBDMType.BOOL)

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@expect_ok
	@disconnect_after
	def rename_file(self, remote_path_before: str, remote_path_after: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!sysfileupd")
		cmd.set_param("name", remote_path_after, XBDMType.QUOTED_STRING)
		cmd.set_param("localsrc", remote_path_before, XBDMType.QUOTED_STRING)

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@expect_ok
	@disconnect_after
	def draw_text(self, s: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!drawtext")
		cmd.set_param("text", s, XBDMType.QUOTED_STRING)

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@disconnect_after
	def version(self) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!version")
		cmd.set_param("verhi", 0x20000, XBDMType.DWORD)
		cmd.set_param("verlo", 0x53080012, XBDMType.DWORD)

		self.send_command(cmd)
		return self.receive_reply()

	@connect_before
	@disconnect_after
	def valid_device(self, base_ver: int, mb_needed: int) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!validdevice")
		cmd.set_param("basesysver", str(base_ver), XBDMType.STRING)
		cmd.set_param("mbneeded", str(mb_needed), XBDMType.STRING)

		self.send_command(cmd)
		return self.receive_reply()

	@connect_before
	@disconnect_after
	def validate_hdd_partitions(self) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!validatehddpartitions")

		self.send_command(cmd)
		return self.receive_reply()

	@connect_before
	@disconnect_after
	def is_flash_clean(self) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!isflashclean")

		self.send_command(cmd)
		return self.receive_reply()

	@connect_before
	@disconnect_after
	def install_recovery_type(self) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!instrecoverytype")

		self.send_command(cmd)
		return self.receive_reply()

	@connect_before
	@expect_ok
	@disconnect_after
	def configure(self, flash_start: int) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!configure")
		cmd.set_param("flashstart", flash_start, XBDMType.DWORD)
		cmd.set_flag("ffs")

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@expect_ok
	@disconnect_after
	def recovery(self, device_index: int) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!recovery")
		cmd.set_param("installver", "17489", XBDMType.STRING)
		cmd.set_param("selectedver", "17489", XBDMType.STRING)
		cmd.set_param("autoupd", "0", XBDMType.BOOL)
		cmd.set_param("rectype", "1", XBDMType.BOOL)
		cmd.set_param("deviceindex", str(device_index), XBDMType.STRING)
		cmd.set_flag("noformathdd")
		cmd.set_flag("formatulrcache")
		cmd.set_flag("formatsysext")
		cmd.set_flag("createsysextrd")

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@expect_ok
	@disconnect_after
	def close_final(self) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!close")
		cmd.set_flag("final")

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@expect_ok
	@disconnect_after
	def flash(self, rom_dir: str, flag: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!flash")
		cmd.set_param("romdir", rom_dir, XBDMType.QUOTED_STRING)
		cmd.set_flag(flag)

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@expect_ok
	@disconnect_after
	def commit_sysext_ramdisk(self, device_index: int) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!commitsysextramdisk")
		cmd.set_param("deviceindex", str(device_index), XBDMType.STRING)

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@disconnect_after
	def get_region(self) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!getregion")

		self.send_command(cmd)
		return self.receive_reply()

	@connect_before
	@expect_ok
	@disconnect_after
	def set_xam_feature_mask(self) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!setxamfeaturemask")

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@expect_ok
	@disconnect_after
	def finish(self) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!finish")

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

	@connect_before
	@expect_ok
	@disconnect_after
	def restart(self) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!restart")

		self.send_command(cmd)
		# self.expect_code(XBDMCode.OK)

class RGLoaderXBDMClient(BaseXBDMClient):
	@connect_before
	@disconnect_after
	def peek_byte(self, addr: int) -> int:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!peekbyte")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.send_command(cmd)
		self.expect_code(XBDMCode.BINARY_RESPONSE_FOLLOWS)
		v = int.from_bytes(self.read(1), "big", signed=False)
		return v

	@connect_before
	@disconnect_after
	def peek_word(self, addr: int) -> int:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!peekword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.send_command(cmd)
		self.expect_code(XBDMCode.BINARY_RESPONSE_FOLLOWS)
		v = int.from_bytes(self.read(2), "big", signed=False)
		return v

	@connect_before
	@disconnect_after
	def peek_dword(self, addr: int) -> int:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!peekdword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.send_command(cmd)
		self.expect_code(XBDMCode.BINARY_RESPONSE_FOLLOWS)
		v = int.from_bytes(self.read(4), "big", signed=False)
		return v

	# @connect_before_and_disconnect_after

	@connect_before
	@disconnect_after
	def peek_qword(self, addr: int) -> int:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!peekqword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.send_command(cmd)
		self.expect_code(XBDMCode.BINARY_RESPONSE_FOLLOWS)
		v = int.from_bytes(self.read(8), "big", signed=False)
		return v

	@connect_before
	@disconnect_after
	def peek_bytes(self, addr: int, size: int) -> bytes:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!peekbytes")
		cmd.set_param("addr", addr, XBDMType.QWORD)
		cmd.set_param("size", size, XBDMType.DWORD)

		self.send_command(cmd)
		self.expect_code(XBDMCode.BINARY_RESPONSE_FOLLOWS)
		data = self.read(size)
		return data

	@connect_before
	@disconnect_after
	def poke_byte(self, addr: int, value: int) -> None:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!pokebyte")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.send_command(cmd)
		self.expect_code(XBDMCode.SEND_BINARY_DATA)
		self.write((value & MASK_UINT8).to_bytes(1, "big", signed=False))

	@connect_before
	@disconnect_after
	def poke_word(self, addr: int, value: int) -> None:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!pokeword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.send_command(cmd)
		self.expect_code(XBDMCode.SEND_BINARY_DATA)
		self.write((value & MASK_UINT16).to_bytes(2, "big", signed=False))

	@connect_before
	@disconnect_after
	def poke_dword(self, addr: int, value: int) -> None:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!pokedword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.send_command(cmd)
		self.expect_code(XBDMCode.SEND_BINARY_DATA)
		self.write((value & MASK_UINT32).to_bytes(4, "big", signed=False))

	@connect_before
	@disconnect_after
	def poke_qword(self, addr: int, value: int) -> None:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!pokeqword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.send_command(cmd)
		self.expect_code(XBDMCode.SEND_BINARY_DATA)
		self.write((value & MASK_UINT64).to_bytes(8, "big", signed=False))

	@connect_before
	@disconnect_after
	def poke_bytes(self, addr: int, value: bytes | bytearray) -> None:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!pokebytes")
		cmd.set_param("addr", addr, XBDMType.QWORD)
		cmd.set_param("size", len(value), XBDMType.DWORD)

		self.send_command(cmd)
		self.expect_code(XBDMCode.SEND_BINARY_DATA)
		self.write(value)

__all__ = [
	# variables
	"XBDM_PORT",
	"XBDM_BUFF_SIZE",
	"XBDM_NEWLINE",

	# classes
	"XBDMCode",
	"XBDMType",
	"XBDMShlex",
	"XBDMCommand",
	"BaseXBDMClient",
	"XBUpdateXBDMClient",
	"RGLoaderXBDMClient",
]