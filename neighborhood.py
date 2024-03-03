#!/usr/bin/env python3

from pathlib import Path

from xbdm_common import *

# arguments
XBDM_HOST = "192.168.1.194"

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