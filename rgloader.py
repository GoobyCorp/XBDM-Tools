#!/usr/bin/env python3

from struct import unpack_from

from xbdm_common import *

XBDM_HOST = "192.168.1.194"

def main() -> int:
	with RGLoaderXBDMClient(XBDM_HOST) as cli:
		"""
		cli.poke_byte(0, 0xFF)
		data = cli.peek_bytes(0, 0x10)
		print(data.hex().upper())

		cli.poke_word(0, 0xFFFF)
		data = cli.peek_bytes(0, 0x10)
		print(data.hex().upper())

		cli.poke_dword(0, 0xFFFFFFFF)
		data = cli.peek_bytes(0, 0x10)
		print(data.hex().upper())

		cli.poke_qword(0, 0xFFFFFFFFFFFFFFFF)
		data = cli.peek_bytes(0, 0x10)
		print(data.hex().upper())

		cli.poke_bytes(0, bytes.fromhex("FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF"))
		data = cli.peek_bytes(0, 0x10)
		print(data.hex().upper())
		"""

		for i in range(12):
			addr = 0x8000020000020000 + (i * 0x200)
			v = cli.peek_qword(addr)
			print(f"{v:X}".rjust(0x10, "0"))

		v = cli.peek_qword(0x200016A08)
		v += 0x400
		exp_tbl_addr = v
		exp_tbl = cli.peek_bytes(exp_tbl_addr, 0x10 * 5)  # max of 5 expansions
		for i in range(0, len(exp_tbl), 0x10):
			(exp_magic, exp_flags, exp_addr) = unpack_from(">2IQ", exp_tbl, i)
			if exp_magic == 0 and exp_flags == 0 and exp_addr == 0:
				break
			exp_size_addr = exp_addr + 8
			exp_code_addr = exp_addr + 0x10
			exp_size = cli.peek_dword(exp_size_addr)
			exp_code = cli.peek_bytes(exp_code_addr, exp_size - 4)

			print(exp_magic.to_bytes(4, "big").decode("UTF8"))
			print(f"0x{exp_size:X}")
			print(exp_code.hex().upper())

	return 0

if __name__ == "__main__":
	exit(main())