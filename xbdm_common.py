import asyncio
from io import BytesIO
from shlex import shlex, split
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

# constants
FACILITY_XBDM = 0x2DA
MASK_UINT8 = 0xFF
MASK_UINT16 = 0xFFFF
MASK_UINT32 = 0xFFFFFFFF
MASK_UINT64 = 0xFFFFFFFFFFFFFFFF

# lambdas
MAKE_HRESULT = lambda x, y, z: (x << 31) | (y << 16) | z
XBDM_HRESERR = lambda x: MAKE_HRESULT(1, FACILITY_XBDM, x)
XBDM_HRESSUCC = lambda x: MAKE_HRESULT(0, FACILITY_XBDM, x)

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

class XBDMCode(IntEnum):
	OK = 200
	CONNECTED = 201
	MULTILINE_RESPONSE_FOLLOWS = 202
	BINARY_RESPONSE_FOLLOWS = 203
	SEND_BINARY_DATA = 204
	ERROR_NO_SUCH_FILE = 402
	ERROR = 405
	ERROR_PATH_NOT_FOUND = 430

class XBDMType(IntEnum):
	NONE = 0
	INTEGER = 1
	DWORD = 2
	QWORD = 3
	BYTES = 4
	STRING = 5
	QUOTED_STRING = 6

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
		self.quotes = '"'
		# self.whitespace = " \t"
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
		elif t == XBDMType.STRING:
			assert isinstance(value, str)
		elif t == XBDMType.INTEGER:
			assert isinstance(value, int)

	def value_to_type(self, value: str) -> XBDMType:
		if value.startswith("0x"):
			t = XBDMType.DWORD
		elif value.startswith("0q"):
			t = XBDMType.QWORD
		elif " " in value or value.startswith('"') or value.startswith("'"):
			t = XBDMType.QUOTED_STRING
		else:
			try:
				v = int(value)
				t = XBDMType.INTEGER
			except:
				t = XBDMType.QUOTED_STRING
		return t

	def value_to_output(self, value: Any, t: XBDMType) -> str:
		if t == XBDMType.DWORD:
			if value == 0:
				value = "0x0"
			else:
				value = "0x" + value.to_bytes(4, "big").hex().upper().lstrip("0")
		elif t == XBDMType.QWORD:
			if value == 0:
				value = "0q0"
			else:
				value = "0q" + value.to_bytes(8, "big").hex().upper().lstrip("0")
		elif t == XBDMType.QUOTED_STRING:
			value = f'"{value}"'
		elif t == XBDMType.INTEGER:
			value = str(value)
		return value

	def value_apply_type(self, value: str, t: XBDMType) -> Any:
		if t == XBDMType.DWORD:
			if value.startswith("0x"):
				value = value[2:]
				value = value.rjust(8, "0")
				value = int.from_bytes(bytes.fromhex(value), "big")
			else:
				value = int(value)
		elif t == XBDMType.QWORD:
			if value.startswith("0x") or value.startswith("0q"):
				value = value[2:]
				value = value.rjust(16, "0")
				value = int.from_bytes(bytes.fromhex(value), "big")
			else:
				value = int(value)
		elif t == XBDMType.QUOTED_STRING:
			pass
		elif t == XBDMType.INTEGER:
			value = int(value)
		return value

	@staticmethod
	def parse(command: str):
		cmd = XBDMCommand()
		sh = XBDMShlex(command)
		parts = list(sh)

		idx = 0
		if parts[0].endswith("-"):  # response
			cmd.set_code(int(parts[0][:-1]))
			idx += 1
		elif "=" in parts[0]:  # multiline string
			pass
		else:  # command
			cmd.set_name(parts[0])
			idx += 1

		if len(parts) > 0:
			for single in parts[idx:]:
				if "=" in single:  # key/value pair
					(key, value) = single.split("=", 1)
					t = cmd.value_to_type(value)
					v = cmd.value_apply_type(value, t)
					cmd.set_param(key, v, t)
				else:  # flag
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
		return key in self.flags

	def param_exists(self, key: str, lc_check: bool = True) -> bool:
		return self.get_param(key, lc_check) is not None

	def set_flag(self, key: str) -> None:
		if key not in self.flags:
			self.flags.append(key)

	def set_param(self, key: str, value: Any, t: XBDMType) -> None:
		# key = key.lower()
		self.enforce_types(value, t)
		self.args[key] = (value, t)

	def get_params(self) -> dict:
		return self.args

	def get_param(self, key: str, lc_check: bool = True) -> Any | None:
		val0 = self.args.get(key)
		val1 = self.args.get(key.lower())

		if not lc_check and val0 is not None:
			return val0[0]
		elif lc_check and val0 is None and val1 is not None:
			return val1[0]
		elif val0 is not None:
			return val0[0]
		elif val1 is not None:
			return val1[0]

	def get_output(self, as_bytes: bool = False, line_ending: bool = True) -> str | bytes:
		o = ""
		ml = False
		if self.name is not None:  # commands only
			o = self.name
		if self.code is not None and self.code != 0:  # replies only
			o = str(self.code) + "-"

		if self.name is None and (self.code is None or self.code == 0):  # multiline string
			ml = True

		if len(self.args) > 0:
			if not ml:
				o += " "
			o += " ".join([f"{k}={self.value_to_output(v, t)}" for (k, (v, t)) in self.args.items()])
		if len(self.flags) > 0:
			o += " "
			o += " ".join(self.flags)
		if line_ending:
			o += "\r\n"
		if as_bytes:
			return o.encode("UTF8")
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
				bl -= bio.write(tmp)
				return bio.getvalue()

	async def read_to(self, dst: BinaryIO, size: int) -> None:
		bl = size
		while bl > 0:
			if bl < XBDM_BUFF_SIZE:
				tmp = await self.reader.read(bl)
			else:
				tmp = await self.reader.read(XBDM_BUFF_SIZE)
			if not tmp:
				break
			bl -= dst.write(tmp)

	async def write(self, data: bytes | bytearray) -> None:
		bl = len(data)
		with BytesIO(data) as bio:
			while bl > 0:
				if bl < XBDM_BUFF_SIZE:
					self.writer.write(bio.read(bl))
					bl -= bl
				else:
					self.writer.write(bio.read(XBDM_BUFF_SIZE))
					bl -= XBDM_BUFF_SIZE
				await self.writer.drain()

	async def write_from(self, src: BinaryIO, size: int) -> None:
		bl = size
		while bl > 0:
			if bl < XBDM_BUFF_SIZE:
				self.writer.write(src.read(bl))
				bl -= bl
			else:
				self.writer.write(src.read(XBDM_BUFF_SIZE))
				bl -= XBDM_BUFF_SIZE
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

	def disconnect_with_bye(self) -> None:
		self.send_bye()
		self.disconnect()

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

	def read_to(self, dst: BinaryIO, size: int) -> None:
		return self.loop.run_until_complete(self.__async__read_to(dst, size))

	async def __async__read_to(self, dst: BinaryIO, size: int) -> None:
		async with self.axc as cli:
			await cli.read_to(dst, size)

	def write(self, data: bytes | bytearray) -> None:
		self.loop.run_until_complete(self.__async__write(data))

	async def __async__write(self, data: bytes | bytearray) -> None:
		async with self.axc as cli:
			await cli.write(data)

	def write_from(self, src: BinaryIO, size: int) -> None:
		self.loop.run_until_complete(self.__async__write_from(src, size))

	async def __async__write_from(self, src: BinaryIO, size: int) -> None:
		async with self.axc as cli:
			await cli.write_from(src, size)

	def read_multi_lines(self) -> list[bytes]:
		lines = []
		while (line := self.readline()) != (b"." + XBDM_NEWLINE):
			lines.append(line)
		return lines

	def read_multi_data(self) -> bytes:
		return b"".join([bytes.fromhex(x.decode("ASCII")) for x in self.read_multi_lines()])

	def read_multi_commands(self) -> list[XBDMCommand]:
		return [XBDMCommand.parse(x.decode("ASCII")) for x in self.read_multi_lines()]

	def writefileobj(self, src: BinaryIO) -> None:
		copyfileobj(src, self, XBDM_BUFF_SIZE)

	def readfileobj(self, dst: BinaryIO) -> None:
		copyfileobj(self, dst, XBDM_BUFF_SIZE)

	def send_command(self, cmd: XBDMCommand) -> None:
		self.write(cmd.get_output(True))

	def send_bye(self) -> None:
		self.write(XBDM_BYE)

	def expect_reply(self) -> XBDMCommand:
		return XBDMCommand.parse(self.readline().decode("ASCII"))

	def expect_reply_with_code(self, code: XBDMCode | int) -> XBDMCommand:
		rep = self.expect_reply()
		assert rep.code == code, f"Expected {code}, got {rep.code}"
		return rep

	def expect_reply_with_codes(self, codes: list[XBDMCode | int]) -> int:
		rep = XBDMCommand.parse(self.readline().decode("ASCII"))
		assert rep.code in codes, f"{rep.code} not in {', '.join([str(x.value) for x in codes])}"
		return rep.code

	def expect_code(self, code: XBDMCode | int) -> None:
		rep = XBDMCommand.parse(self.readline().decode("ASCII"))
		assert rep.code == code, f"Expected {code}, got {rep.code}"

	def expect_ok(self) -> None:
		self.expect_code(XBDMCode.OK)

	def expect_multiline_response(self) -> None:
		self.expect_code(XBDMCode.MULTILINE_RESPONSE_FOLLOWS)

	def expect_binary_response(self) -> None:
		self.expect_code(XBDMCode.BINARY_RESPONSE_FOLLOWS)

	def expect_send_binary(self) -> None:
		self.expect_code(XBDMCode.SEND_BINARY_DATA)

	def recovery(self) -> None:
		cmd = XBDMCommand()
		cmd.set_name("recovery")

		self.connect_and_check()
		self.send_command(cmd)
		self.disconnect()

	def get_file_attributes(self, remote_path: str) -> XBDMCommand | None:
		cmd = XBDMCommand()
		cmd.set_name("getfileattributes")
		cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)

		self.connect_and_check()
		self.send_command(cmd)
		code = self.expect_reply_with_codes([XBDMCode.MULTILINE_RESPONSE_FOLLOWS, XBDMCode.ERROR_NO_SUCH_FILE])
		ret = None
		if code == XBDMCode.MULTILINE_RESPONSE_FOLLOWS:
			reps = self.read_multi_commands()
			return reps[0]
		else:
			pass
		self.disconnect_with_bye()
		return ret

	def file_exists(self, remote_path: str) -> bool:
		ret = self.get_file_attributes(remote_path)
		return ret is not None

	def dirlist(self, remote_path: str) -> list[XBDMCommand]:
		cmd = XBDMCommand()
		cmd.set_name("dirlist")
		cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)

		self.connect_and_check()
		self.send_command(cmd)
		rep = self.expect_reply_with_codes([XBDMCode.MULTILINE_RESPONSE_FOLLOWS, XBDMCode.ERROR_NO_SUCH_FILE])
		if rep == XBDMCode.MULTILINE_RESPONSE_FOLLOWS:
			lines = self.read_multi_commands()
		else:
			lines = []
		self.disconnect_with_bye()
		return lines

	def mkdir(self, remote_path: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("mkdir")
		cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def rename(self, old_remote_path: str, new_remote_path: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("mkdir")
		cmd.set_param("NAME", old_remote_path, XBDMType.QUOTED_STRING)
		cmd.set_param("NEWNAME", new_remote_path, XBDMType.QUOTED_STRING)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def delete(self, remote_path: str) -> bool:
		cmd = XBDMCommand()
		cmd.set_name("delete")
		cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)

		self.connect_and_check()
		self.send_command(cmd)
		code = self.expect_reply_with_codes([XBDMCode.OK, XBDMCode.ERROR_NO_SUCH_FILE])
		ret = False
		if code == XBDMCode.OK:
			ret = True
		elif code == XBDMCode.ERROR_NO_SUCH_FILE:
			pass
		self.disconnect_with_bye()
		return ret

	def send_file(self, local_path: str, remote_path: str) -> bool:
		lp = Path(local_path)

		assert lp.exists() and lp.is_file(), "Local file doesn't exist!"

		ls = lp.stat().st_size
		cmd = XBDMCommand()
		cmd.set_name("SENDFILE")
		cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)
		cmd.set_param("LENGTH", ls, XBDMType.DWORD)

		self.connect_and_check()
		self.send_command(cmd)
		code = self.expect_reply_with_codes([XBDMCode.SEND_BINARY_DATA, XBDMCode.ERROR_PATH_NOT_FOUND])
		ret = False
		if code == XBDMCode.SEND_BINARY_DATA:
			with lp.open("rb") as lf:
				self.writefileobj(lf)
			self.expect_ok()
			ret = True
		else:
			pass
		self.disconnect_with_bye()
		return ret

	def get_file(self, remote_path: str, local_path: str) -> bool:
		lp = Path(local_path)

		cmd = XBDMCommand()
		cmd.set_name("GETFILE")
		cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)

		self.connect_and_check()
		self.send_command(cmd)
		code = self.expect_reply_with_codes([XBDMCode.BINARY_RESPONSE_FOLLOWS, XBDMCode.ERROR_NO_SUCH_FILE])
		ret = False
		if code == XBDMCode.BINARY_RESPONSE_FOLLOWS:
			(size,) = unpack("<I", self.read(4))
			with lp.open("wb") as lf:
				self.read_to(lf, size)
			ret = True
		else:
			pass
		self.disconnect_with_bye()
		return ret

	def magic_boot(self, flag: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("magicboot")
		cmd.set_flag(flag)

		self.connect_and_check()
		self.send_command(cmd)
		self.disconnect()

	def read_memory(self, addr: int, size: int) -> bytes:
		cmd = XBDMCommand()
		cmd.set_name("getmem")
		cmd.set_param("ADDR", addr, XBDMType.DWORD)
		cmd.set_param("LENGTH", size, XBDMType.DWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_multiline_response()
		data = self.read_multi_data()
		self.disconnect_with_bye()
		return data

	def write_memory(self, addr: int, data: bytes | bytearray) -> None:
		cmd = XBDMCommand()
		cmd.set_name("setmem")
		cmd.set_param("addr", addr, XBDMType.DWORD)
		cmd.set_param("data", data.hex().upper(), XBDMType.STRING)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

class XBUpdateXBDMClient(BaseXBDMClient):
	def system_file_update(self, local_path: str, remote_path: str) -> None:
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

			self.connect_and_check()
			self.send_command(cmd)
			self.expect_code(XBDMCode.SEND_BINARY_DATA)
			self.writefileobj(lf)
			self.expect_ok()
			self.disconnect_with_bye()
		# self.expect_code(XBDMCode.OK)

	def delete_file(self, remote_path: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!sysfileupd")
		cmd.set_param("name", remote_path, XBDMType.QUOTED_STRING)
		cmd.set_param("remove", "1", XBDMType.INTEGER)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def delete_dir(self, remote_path: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!sysfileupd")
		cmd.set_param("name", remote_path, XBDMType.QUOTED_STRING)
		cmd.set_param("removedir", "1", XBDMType.INTEGER)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def rename_file(self, remote_path_before: str, remote_path_after: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!sysfileupd")
		cmd.set_param("name", remote_path_after, XBDMType.QUOTED_STRING)
		cmd.set_param("localsrc", remote_path_before, XBDMType.QUOTED_STRING)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def draw_text(self, s: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!drawtext")
		cmd.set_param("text", s, XBDMType.QUOTED_STRING)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def version(self) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!version")
		cmd.set_param("verhi", 0x20000, XBDMType.DWORD)
		cmd.set_param("verlo", 0x53080012, XBDMType.DWORD)

		self.connect_and_check()
		self.send_command(cmd)
		rep = self.expect_reply()
		self.disconnect_with_bye()
		return rep

	def valid_device(self, base_ver: int, mb_needed: int) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!validdevice")
		cmd.set_param("basesysver", str(base_ver), XBDMType.STRING)
		cmd.set_param("mbneeded", str(mb_needed), XBDMType.STRING)

		self.connect_and_check()
		self.send_command(cmd)
		rep = self.expect_reply()
		self.disconnect_with_bye()
		return rep

	def validate_hdd_partitions(self) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!validatehddpartitions")

		self.connect_and_check()
		self.send_command(cmd)
		rep = self.expect_reply()
		self.disconnect_with_bye()
		return rep

	def is_flash_clean(self) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!isflashclean")

		self.connect_and_check()
		self.send_command(cmd)
		rep = self.expect_reply()
		self.disconnect_with_bye()
		return rep

	def install_recovery_type(self) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!instrecoverytype")

		self.connect_and_check()
		self.send_command(cmd)
		rep = self.expect_reply()
		self.disconnect_with_bye()
		return rep

	def configure(self, flash_start: int) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!configure")
		cmd.set_param("flashstart", flash_start, XBDMType.DWORD)
		cmd.set_flag("ffs")

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def recovery(self, device_index: int) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!recovery")
		cmd.set_param("installver", 17489, XBDMType.INTEGER)
		cmd.set_param("selectedver", 17489, XBDMType.INTEGER)
		cmd.set_param("autoupd", 0, XBDMType.INTEGER)
		cmd.set_param("rectype", 1, XBDMType.INTEGER)
		cmd.set_param("deviceindex", device_index, XBDMType.INTEGER)
		cmd.set_flag("noformathdd")
		cmd.set_flag("formatulrcache")
		cmd.set_flag("formatsysext")
		cmd.set_flag("createsysextrd")

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def close_final(self) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!close")
		cmd.set_flag("final")

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def flash(self, rom_dir: str, flag: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!flash")
		cmd.set_param("romdir", rom_dir, XBDMType.QUOTED_STRING)
		cmd.set_flag(flag)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def commit_sysext_ramdisk(self, device_index: int) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!commitsysextramdisk")
		cmd.set_param("deviceindex", str(device_index), XBDMType.STRING)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def get_region(self) -> XBDMCommand:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!getregion")

		self.connect_and_check()
		self.send_command(cmd)
		rep = self.expect_reply()
		self.disconnect_with_bye()
		return rep

	def set_xam_feature_mask(self) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!setxamfeaturemask")

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def finish(self) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!finish")

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def restart(self) -> None:
		cmd = XBDMCommand()
		cmd.set_name("xbupdate!restart")

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

class RGLoaderXBDMClient(BaseXBDMClient):
	def peek_byte(self, addr: int) -> int:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!peekbyte")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_binary_response()
		v = int.from_bytes(self.read(1), "big", signed=False)
		self.disconnect_with_bye()
		return v

	def peek_word(self, addr: int) -> int:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!peekword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_binary_response()
		v = int.from_bytes(self.read(2), "big", signed=False)
		self.disconnect_with_bye()
		return v

	def peek_dword(self, addr: int) -> int:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!peekdword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_binary_response()
		v = int.from_bytes(self.read(4), "big", signed=False)
		self.disconnect_with_bye()
		return v

	def peek_qword(self, addr: int) -> int:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!peekqword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_binary_response()
		v = int.from_bytes(self.read(8), "big", signed=False)
		self.disconnect_with_bye()
		return v

	def peek_bytes(self, addr: int, size: int) -> bytes:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!peekbytes")
		cmd.set_param("addr", addr, XBDMType.QWORD)
		cmd.set_param("size", size, XBDMType.DWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_binary_response()
		data = self.read(size)
		self.disconnect_with_bye()
		return data

	def poke_byte(self, addr: int, value: int) -> None:
		value &= MASK_UINT8

		cmd = XBDMCommand()
		cmd.set_name("rgloader!pokebyte")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_send_binary()
		self.write((value & MASK_UINT8).to_bytes(1, "big", signed=False))
		self.disconnect_with_bye()

	def poke_word(self, addr: int, value: int) -> None:
		value &= MASK_UINT16

		cmd = XBDMCommand()
		cmd.set_name("rgloader!pokeword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_send_binary()
		self.write((value & MASK_UINT16).to_bytes(2, "big", signed=False))
		self.disconnect_with_bye()

	def poke_dword(self, addr: int, value: int) -> None:
		value &= MASK_UINT32

		cmd = XBDMCommand()
		cmd.set_name("rgloader!pokedword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_send_binary()
		self.write((value & MASK_UINT32).to_bytes(4, "big", signed=False))
		self.disconnect_with_bye()

	def poke_qword(self, addr: int, value: int) -> None:
		value &= MASK_UINT64

		cmd = XBDMCommand()
		cmd.set_name("rgloader!pokeqword")
		cmd.set_param("addr", addr, XBDMType.QWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_send_binary()
		self.write((value & MASK_UINT64).to_bytes(8, "big", signed=False))
		self.disconnect_with_bye()

	def poke_bytes(self, addr: int, value: bytes | bytearray) -> None:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!pokebytes")
		cmd.set_param("addr", addr, XBDMType.QWORD)
		cmd.set_param("size", len(value), XBDMType.DWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_send_binary()
		self.write(value)
		self.expect_ok()
		self.disconnect_with_bye()

	def load_module(self, remote_path: str) -> None:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!loadmodule")
		cmd.set_param("path", remote_path, XBDMType.QUOTED_STRING)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

	def install_expansion(self, data: bytes | bytearray) -> None:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!installexpansion")
		cmd.set_param("size", len(data), XBDMType.DWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_send_binary()
		self.write(data)
		self.disconnect_with_bye()

	def dump_expansions(self, data: bytes | bytearray) -> None:
		cmd = XBDMCommand()
		cmd.set_name("rgloader!dumpexpansions")
		cmd.set_param("size", len(data), XBDMType.DWORD)

		self.connect_and_check()
		self.send_command(cmd)
		self.expect_ok()
		self.disconnect_with_bye()

__all__ = [
	# variables
	"XBDM_PORT",
	"XBDM_BUFF_SIZE",
	"XBDM_NEWLINE",

	# enums
	"XBDMCode",
	"XBDMType",

	# classes
	"XBDMShlex",
	"XBDMCommand",
	"BaseXBDMClient",
	"XBUpdateXBDMClient",
	"RGLoaderXBDMClient",
]