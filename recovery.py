#!/usr/bin/env python3

from time import sleep
from json import loads
from pathlib import Path
from argparse import ArgumentParser

from xbdm_common import *

# xbdm variables
XBDM_PORT = 730
XBDM_BUFF_SIZE = 1460
XBDM_DIR = "DEVICES"
XBDM_NEWLINE = b"\r\n"

# constants
MANIFEST_FILE = "recovery_manifest_21256_18.json"

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
	print(str(p))
	# p.parent.mkdir(parents=True, exist_ok=True)
	return str(p)

def main() -> int:
	parser = ArgumentParser(description="A script to recover Xbox 360 devkits")
	parser.add_argument("host", type=str, help="The devkit IP address")
	parser.add_argument("image", type=str, help="The shadowboot image to install to flash")
	args = parser.parse_args()

	assert Path(args.image).is_file(), "Shadowboot image doesn't exist!"

	mf = read_manifest()

	with XBUpdateXBDMClient(args.host) as cli:
		# BaseXBDMClient.upload_file(cli, xbdm_to_device_path("\\Device\\Flash\\xbupdate.xex"), "\\Device\\Flash\\xbupdate.xex")
		# cli.send_file(str(Path(XBDM_DIR) / "xbupdate.xex"), "\\Device\\Flash\\xbupdate.xex")

		# BaseXBDMClient.recovery(cli)

		# print("Waiting 30 seconds for recovery to boot...")
		# sleep(30)

		cli.draw_text("UwU")

		rep = cli.version()

		rep = cli.valid_device(1888, 210)

		dev_valid = rep.get_param("valid")
		dev_idx = rep.get_param("deviceindex")

		assert dev_valid, "No valid device found to write recovery to!"

		rep = cli.validate_hdd_partitions()

		hdd_valid = rep.get_param("valid") == 1

		assert hdd_valid, "No valid device found to write recovery to!"

		rep = cli.is_flash_clean()

		flash_valid = rep.flag_exists("TRUE")

		assert flash_valid, "Flash isn't clean!"

		rep = cli.install_recovery_type()

		rectyp = rep.get_param("recoverytype")  # .as_int()
		hres = rep.get_param("hresult")  # .as_int()

		assert rectyp, "Invalid recovery type!"

		cli.version()

		cli.configure(0x200000)

		cli.recovery(dev_idx)

		# delete files
		for remote_path in mf["upd_files_to_delete"]:
			cli.delete_file(remote_path)

		# delete directories
		for remote_path in mf["upd_dirs_to_delete"]:
			cli.delete_dir(remote_path)

		# upload files
		# shadowboot
		cli.system_file_update(args.image, "\\Device\\Harddisk0\\Partition1\\xboxrom_update.bin")

		# system files
		for remote_path in mf["upd_files_to_upload_default"]:
			cli.system_file_update(xbdm_to_device_path(remote_path), remote_path)

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
		cli.close_final()

		cli.flash("\\Device\\Harddisk0\\Partition3\\ROM", "enum")
		cli.flash("\\Device\\Harddisk0\\Partition3\\ROM\\0000", "query")

		cli.commit_sysext_ramdisk(dev_idx)

		cli.get_region()

		cli.set_xam_feature_mask()

		cli.finish()

		cli.restart()

		cli.magic_boot("cold")

	return 0

if __name__ == "__main__":
	exit(main())