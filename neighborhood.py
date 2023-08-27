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
XBDM_HOST = "192.168.1.194"

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

def main() -> int:
	lp = Path(r"D:\Games\Xbox 360\Games\Modern Warfare 2\Disc 1")
	rp = r"\Device\Harddisk0\Partition1\Games\Modern Warfare 2"

	with BaseXBDMClient(XBDM_HOST) as cli:
		cli.mkdir(rp)

		for x in lp.rglob("*"):
			if x.is_dir():
				cli.mkdir(rp + "\\" + str(x.relative_to(lp)))

		for x in lp.rglob("*"):
			if x.is_file():
				cli.send_file(str(x), rp + "\\" + str(x.relative_to(lp)))

	return 0

if __name__ == "__main__":
	exit(main())