#!/usr/bin/env python3

import asyncio
from pathlib import Path

from xbdm_common import *

# xbdm variables
XBDM_PORT = 730
XBDM_BUFF_SIZE = 1460
XBDM_DIR = "DEVICES"
XBDM_NEWLINE = b"\r\n"

# arguments
XBDM_HOST: str = ""

def format_response(command: bytes | bytearray, lowercase: bool = False):
	command = command.decode("UTF8").rstrip()
	if lowercase:
		command = command.lower()
	return command

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
		cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)
		cmd.set_param("LENGTH", fs, XBDMType.DWORD)

		# send command
		writer.write(cmd.get_output(True))
		await writer.drain()

		# receive response
		data = await reader.readuntil(XBDM_NEWLINE)
		pkt1 = XBDMCommand.parse(format_response(data))

		if pkt1.code == 430:  # path not found
			pt = Path(remote_path).parent
			await send_xbdm_mkdir(str(pt))

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

async def send_xbdm_getfileattributes(remote_path: str) -> None:
	(reader, writer) = await open_xbdm_connection()

	cmd = XBDMCommand()
	cmd.set_name("mkdir")
	cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)
	# cmd.set_param("LENGTH", fs)

	# print(cmd.get_output(False, False))

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt = XBDMCommand.parse(format_response(data))

	assert pkt.code == 200

	await close_xbdm_connection(reader, writer)

async def send_xbdm_mkdir(remote_path: str) -> None:
	(reader, writer) = await open_xbdm_connection()

	cmd = XBDMCommand()
	cmd.set_name("mkdir")
	cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)
	# cmd.set_param("LENGTH", fs)

	# print(cmd.get_output(False, False))

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt = XBDMCommand.parse(format_response(data))

	assert pkt.code == 200

	await close_xbdm_connection(reader, writer)

async def send_xbdm_dirlist(remote_path: str) -> tuple[list[str], list[str]] | int:
	(reader, writer) = await open_xbdm_connection()

	cmd = XBDMCommand()
	cmd.set_name("dirlist")
	cmd.set_param("NAME", remote_path, XBDMType.QUOTED_STRING)
	# cmd.set_param("LENGTH", fs)

	# print(cmd.get_output(False, False))

	# send command
	writer.write(cmd.get_output(True))
	await writer.drain()

	# receive response
	data = await reader.readuntil(XBDM_NEWLINE)
	pkt1 = XBDMCommand.parse(format_response(data))

	if pkt1.code == 202:  # receive directory listing
		# receive lines
		files = []
		dirs = []
		while True:
			data = await reader.readuntil(XBDM_NEWLINE)
			if data == (b"." + XBDM_NEWLINE):
				break
			pkt2 = XBDMCommand.parse(format_response(data))
			# print(pkt2.get_output(False, False))
			if pkt2.flag_exists("directory"):
				dirs.append(pkt2.get_param("name"))
			else:
				files.append(pkt2.get_param("name"))
		return (dirs, files)

	await close_xbdm_connection(reader, writer)

	return pkt1.code  # directory not found (402)

async def xbdm_neighborhood_client():
	lp = Path(r"D:\Games\Xbox 360\Games\Modern Warfare 2\Disc 1")
	rp = r"\Device\Harddisk0\Partition1\Games\Modern Warfare 2"

	await send_xbdm_mkdir(rp)

	for x in lp.rglob("*"):
		if x.is_dir():
			await send_xbdm_mkdir(rp + "\\" + str(x.relative_to(lp)))

	for x in lp.rglob("*"):
		if x.is_file():
			await send_xbdm_upload_file(str(x), rp + "\\" + str(x.relative_to(lp)))

def main() -> int:
	global XBDM_HOST

	XBDM_HOST = "192.168.1.194"

	asyncio.run(xbdm_neighborhood_client())

	return 0

if __name__ == "__main__":
	exit(main())