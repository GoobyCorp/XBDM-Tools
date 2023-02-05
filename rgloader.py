#!/usr/bin/env python3

import re
import asyncio
from typing import Any
from shlex import shlex

# xbdm variables
XBDM_HOST = "192.168.1.67"
XBDM_PORT = 730
XBDM_BUFF_SIZE = 1460
XBDM_NEWLINE = b"\r\n"

# regex
CODE_EXP = re.compile(r"^(\d+)-")

def format_response(command: bytes | bytearray, lowercase: bool = False):
	command =  command.decode("UTF8").rstrip()
	if lowercase:
		command = command.lower()
	return command

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
	def parse(command: str | bytes | bytearray):
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

async def send_xbdm_command(cmd: XBDMCommand) -> XBDMCommand | bytes:
	(reader, writer) = await open_xbdm_connection()

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt1 = XBDMCommand.parse(format_response(data))

	if pkt1.code == 203:  # binary response
		data = await reader.read(XBDM_BUFF_SIZE)

	if cmd.name in ["recovery", "magicboot"]:
		writer.close()
	else:
		await close_xbdm_connection(reader, writer)

	# return response packet
	if pkt1.code == 203:  # binary response
		return data
	return pkt1

async def xbdm_rgloader_client():
	cmd = XBDMCommand()
	cmd.set_name("rgloader!peekqword")
	for i in range(12):
		cmd.set_param("addr", 0x8000020000020000 + (i * 0x200))
		# print(cmd.get_output(False, False))
		res = await send_xbdm_command(cmd)
		print(res.hex().upper())
def main() -> int:
	asyncio.run(xbdm_rgloader_client())

	return 0

if __name__ == "__main__":
	exit(main())