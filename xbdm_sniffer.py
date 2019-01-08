#this script requires WinPcap and winpcapy
#this script was written because people think that obfuscating a RTE tool is protecting it

import logging
from io import BytesIO
from struct import unpack
from os.path import isfile
from argparse import ArgumentParser
from binascii import hexlify as _hexlify

from winpcapy import WinPcapDevices, WinPcapUtils

XBDM_PORT = 730

#data that's pointless to log
#put one piece of a command per line and it will filter it out from the response
POINTLESS_DATA = []

# the logger
logging.basicConfig(filename='xbdm.log',level=logging.INFO)

def hexlify(b: (bytes, bytearray)) -> str:
    return str(_hexlify(b), "utf8")

def packet_callback(win_pcap, param, header, pkt_data):
    #read the entire packet
    bio = BytesIO(pkt_data)

    #seek to IP frame
    bio.seek(14)
    ip_frame = bio.read(20)
    ip_frame_bio = BytesIO(ip_frame)

    #seek to TCP frame
    bio.seek(0x22)
    tcp_frame = bio.read(20)
    tcp_payload = bio.read()
    tcp_frame_bio = BytesIO(tcp_frame)
    bio.close()

    #seek to IP addresses and parse them
    ip_frame_bio.seek(0x0C)
    src_ip = ".".join([str(b) for b in ip_frame_bio.read(4)])
    dst_ip = ".".join([str(b) for b in ip_frame_bio.read(4)])
    ip_frame_bio.close()

    #format source and destination ports to unsigned shorts
    src_port = unpack("!H", tcp_frame_bio.read(2))[0]
    dst_port = unpack("!H", tcp_frame_bio.read(2))[0]
    tcp_frame_bio.close()

    #log according to arguments
    if src_port == XBDM_PORT or dst_port == XBDM_PORT:
        if args.everything or dst_port == XBDM_PORT:
            #make sure the payload isn't empty and it's a valid XBDM command
            if tcp_payload != b"":  # and tcp_payload.endswith(b"\r\n"):
                #remove line endings and decode to UTF-8
                #tcp_payload = tcp_payload.rstrip().decode("utf8")
                #too congested otherwise
                if not any([(x in tcp_payload) for x in POINTLESS_DATA]):
                    if src_port == XBDM_PORT:
                        print("RECEIVING")
                        logging.info("RECEIVING")
                    elif dst_port == XBDM_PORT:
                        print("SENDING")
                        logging.info("SENDING")
                    print("%s:%s -> %s:%s" % (src_ip, src_port, dst_ip, dst_port))
                    print(tcp_payload)
                    logging.info(tcp_payload)
                    print(hexlify(tcp_payload))
                    logging.info(hexlify(tcp_payload))
                    print("=" * 64)

if __name__ == "__main__":
    #arg parser
    parser = ArgumentParser(description="A script to help reverse RTE tools")
    parser.add_argument("-a", "--adapter", type=str, help="The network adapter name you want to listen on")  #"Intel(R) I210 Gigabit Network Connection"
    parser.add_argument("-f", "--filter-file", default="filter.txt", type=str, help="The file you want to load filters from")
    parser.add_argument("-e", "--everything", action="store_true", help="Log everything")
    parser.add_argument("-l", "--list", action="store_true", help="List network adapters")
    args = parser.parse_args()
    if args.list:
        print("\n".join([x for x in WinPcapDevices.list_devices().values() if x != ""]))
    else:
        #load the filter file or create it if it doesn't exist already
        if isfile(args.filter_file):
            POINTLESS_DATA = [x.rstrip() for x in open(args.filter_file, "r").readlines()]
        else:
            open(args.filter_file, "w").write("")
        #start listening on my main ethernet adapter
        WinPcapUtils.capture_on(args.adapter, packet_callback)