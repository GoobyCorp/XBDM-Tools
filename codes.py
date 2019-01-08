from ctypes import c_ulong
from struct import pack, unpack
from binascii import hexlify as _hexlify

FACILITY_XBDM = 0x2DA

"""
_HRESULT_TYPEDEF_(0x02DA0000)    # No error occurred.

_HRESULT_TYPEDEF_(0x82DA0000)    # An undefined error has occurred.
_HRESULT_TYPEDEF_(0x82DA0001)    # The maximum number of connections has been exceeded.
_HRESULT_TYPEDEF_(0x82DA0002)    # No such file exists.
_HRESULT_TYPEDEF_(0x82DA0003)    # No such module exists.
_HRESULT_TYPEDEF_(0x82DA0004)    # The referenced memory has been unmapped.
_HRESULT_TYPEDEF_(0x82DA0005)    # No such thread ID exists.
_HRESULT_TYPEDEF_(0x82DA0006)    # The console clock is not set.
_HRESULT_TYPEDEF_(0x82DA0007)    # An invalid command was specified.
_HRESULT_TYPEDEF_(0x82DA0008)    # Thread not stopped.
_HRESULT_TYPEDEF_(0x82DA0009)    # File must be copied, not moved.
_HRESULT_TYPEDEF_(0x82DA000A)    # A file already exists with the same name.
_HRESULT_TYPEDEF_(0x82DA000B)    # The directory is not empty.
_HRESULT_TYPEDEF_(0x82DA000C)    # An invalid file name was specified.
_HRESULT_TYPEDEF_(0x82DA000D)    # Cannot create the specified file.
_HRESULT_TYPEDEF_(0x82DA000E)    # Cannot access the specified file.
_HRESULT_TYPEDEF_(0x82DA000F)    # The device is full.
_HRESULT_TYPEDEF_(0x82DA0010)    # This title is not debuggable.
_HRESULT_TYPEDEF_(0x82DA0011)    # The counter type is invalid.
_HRESULT_TYPEDEF_(0x82DA0012)    # Counter data is not available.
_HRESULT_TYPEDEF_(0x82DA0014)    # The console is not locked.
_HRESULT_TYPEDEF_(0x82DA0015)    # Key exchange is required.
_HRESULT_TYPEDEF_(0x82DA0016)    # A dedicated connection is required.
_HRESULT_TYPEDEF_(0x82DA0017)    # The argument was invalid.
_HRESULT_TYPEDEF_(0x82DA0018)    # The profile is not started.
_HRESULT_TYPEDEF_(0x82DA0019)    # The profile is already started.
_HRESULT_TYPEDEF_(0x82DA001A)    # The console is already in DMN_EXEC_STOP.
_HRESULT_TYPEDEF_(0x82DA001B)    # FastCAP is not enabled.
_HRESULT_TYPEDEF_(0x82DA001C)    # The Debug Monitor could not allocate memory.
_HRESULT_TYPEDEF_(0x82DA001D)    # Initialization through DmStartProfiling has taken longer than allowed. 
_HRESULT_TYPEDEF_(0x82DA001E)    # The path was not found.
_HRESULT_TYPEDEF_(0x82DA001F)    # The screen input format is invalid.
_HRESULT_TYPEDEF_(0x82DA0020)    # The screen output format is invalid.
_HRESULT_TYPEDEF_(0x82DA0021)    # CallCAP is not enabled.
_HRESULT_TYPEDEF_(0x82DA0022)    # Both FastCAP and CallCAP are enabled in different modules.
_HRESULT_TYPEDEF_(0x82DA0023)    # Neither FastCAP nor CallCAP are enabled.
_HRESULT_TYPEDEF_(0x82DA0024)    # A branched to a section the instrumentation code failed.
_HRESULT_TYPEDEF_(0x82DA0025)    # A necessary field is not present in the header of Xbox 360 title. 
_HRESULT_TYPEDEF_(0x82DA0026)    # Provided data buffer for profiling is too small.
_HRESULT_TYPEDEF_(0x82DA0027)    # The Xbox 360 console is currently rebooting. 
_HRESULT_TYPEDEF_(0x82DA0029)    # The maximum duration was exceeded.
_HRESULT_TYPEDEF_(0x82DA002A)    # The current state of game controller automation is incompatible with the requested action.
_HRESULT_TYPEDEF_(0x82DA002B)    # The maximum number of extensions are already used.
_HRESULT_TYPEDEF_(0x82DA002C)    # The Performance Monitor Counters (PMC) session is already active.
_HRESULT_TYPEDEF_(0x82DA002D)    # The Performance Monitor Counters (PMC) session is not active.
_HRESULT_TYPEDEF_(0x82DA002E)    # The string passed to a debug monitor function, such as DmSendCommand, was too long. The total length of a command string, which includes its null termination and trailing CR/LF must be less than or equal too 512 characters.
_HRESULT_TYPEDEF_(0x82DA0050)    # The current application has an incompatible version of D3D.
_HRESULT_TYPEDEF_(0x82DA0051)    # The D3D surface is not currently valid.
_HRESULT_TYPEDEF_(0x82DA0100)    # Cannot connect to the target system.
_HRESULT_TYPEDEF_(0x82DA0101)    # The connection to the target system has been lost.
_HRESULT_TYPEDEF_(0x82DA0103)    # An unexpected file error has occurred.
_HRESULT_TYPEDEF_(0x82DA0104)    # Used by the DmWalkxxx functions to signal the end of a list. 
_HRESULT_TYPEDEF_(0x82DA0105)    # The buffer referenced was too small to receive the requested data.
_HRESULT_TYPEDEF_(0x82DA0106)    # The file specified is not a valid XBE.
_HRESULT_TYPEDEF_(0x82DA0107)    # Not all requested memory could be written.
_HRESULT_TYPEDEF_(0x82DA0108)    # No target system name has been set.
_HRESULT_TYPEDEF_(0x82DA0109)    # There is no string representation of this error code.
_HRESULT_TYPEDEF_(0x82DA010A)    # The Xbox 360 console returns an formatted status string following a command. When using the custom command processor (see DmRegisterCommandProcessor), it may indicate that console and PC code are not compatible.
_HRESULT_TYPEDEF_(0x82DA0150)    # A previous command is still pending.

_HRESULT_TYPEDEF_(0x02DA0001)    # A connection has been successfully established.
_HRESULT_TYPEDEF_(0x02DA0002)    # One of the three types of continued transactions supported by DmRegisterCommandProcessor.
_HRESULT_TYPEDEF_(0x02DA0003)    # One of the three types of continued transactions supported by DmRegisterCommandProcessor. 
_HRESULT_TYPEDEF_(0x02DA0004)    # One of the three types of continued transactions supported by DmRegisterCommandProcessor. 
_HRESULT_TYPEDEF_(0x02DA0005)    # A connection has been dedicated to a specific threaded command handler.
_HRESULT_TYPEDEF_(0x02DA0006)    # The profiling session has been restarted successfully.
_HRESULT_TYPEDEF_(0x02DA0007)    # Fast call-attribute profiling is enabled.
_HRESULT_TYPEDEF_(0x02DA0008)    # Calling call-attribute profiling is enabled.
_HRESULT_TYPEDEF_(0x02DA0009)    # A result code.
"""

def hexlify(b: (bytes, bytearray)) -> str:
    return str(_hexlify(b), "utf8")

def code_to_hsuccess(code: int) -> int:
    return code_to_hresult(0, FACILITY_XBDM, code)

def code_to_herror(code: int) -> int:
    return code_to_hresult(1, FACILITY_XBDM, code)

def code_to_hresult(sev: int, fac: int, code: int) -> int:
    return (sev << 31) | (fac << 16) | code

def hresult_to_code(hr: int) -> int:
    if (hr >> 16 & 0x7FFF != FACILITY_XBDM):
        hr = XBDMResult.XBDM_NOERR if (hr >= 0) else XBDMResult.XBDM_UNDEFINED
    elif (hr & 0xFFFF > 0xFF):
        hr = XBDMResult.XBDM_UNDEFINED
    failed = bool(hr >> 31)
    szBuf = "4" if failed else "2"
    szBuf += str(0 + int((hr & 0xFFFF) / 10))
    szBuf += str(0 + int((hr & 0xFFFF) % 10))
    return int(szBuf)

def code_to_hex(code: int) -> str:
    return hexlify(pack(">I", code))

class XBDMResult(object):
    #errors
    XBDM_UNDEFINED = code_to_herror(0)
    XBDM_MAXCONNECT = code_to_herror(1)
    XBDM_NOSUCHFILE = [code_to_herror(2), "file not found"]
    XBDM_NOMODULE = [code_to_herror(3), "no such module"]
    XBDM_MEMUNMAPPED = [code_to_herror(4), "memory not mapped"]
    XBDM_NOTHREAD = [code_to_herror(5), "no such thread"]
    XBDM_CLOCKNOTSET = code_to_herror(6)
    XBDM_INVALIDCMD = [code_to_herror(7), "unknown command"]
    XBDM_NOTSTOPPED = [code_to_herror(8), "not stopped"]
    XBDM_MUSTCOPY = [code_to_herror(9), "file must be copied"]
    XBDM_ALREADYEXISTS = [code_to_herror(10), "file already exists"]
    XBDM_DIRNOTEMPTY = [code_to_herror(11), "directory not empty"]
    XBDM_BADFILENAME = [code_to_herror(12), "filename is invalid"]
    XBDM_CANNOTCREATE = [code_to_herror(13), "file cannot be created"]
    XBDM_CANNOTACCESS = [code_to_herror(14), "access denied"]
    XBDM_DEVICEFULL = [code_to_herror(15), "no room on device"]
    XBDM_NOTDEBUGGABLE = [code_to_herror(16), "not debuggable"]
    XBDM_BADCOUNTTYPE = [code_to_herror(17), "type invalid"]
    XBDM_COUNTUNAVAILABLE = [code_to_herror(18), "data not available"]
    XBDM_NOTLOCKED = [code_to_herror(20), "box is not locked"]
    XBDM_KEYXCHG = [code_to_herror(21), "key exchange required"]
    XBDM_MUSTBEDEDICATED = [code_to_herror(22), "dedicated connection required"]
    XBDM_INVALIDARG = code_to_herror(23)
    XBDM_PROFILENOTSTARTED = code_to_herror(24)
    XBDM_PROFILEALREADYSTARTED = code_to_herror(25)
    XBDM_ALREADYSTOPPED = [code_to_herror(26), "already stopped"]
    XBDM_FASTCAPNOTENABLED = code_to_herror(27)
    XBDM_NOMEMORY = code_to_herror(28)
    XBDM_TIMEOUT = code_to_herror(29)
    XBDM_NOSUCHPATH = code_to_herror(30)
    XBDM_INVALID_SCREEN_INPUT_FORMAT = code_to_herror(31)
    XBDM_INVALID_SCREEN_OUTPUT_FORMAT = code_to_herror(32)
    XBDM_CALLCAPNOTENABLED = code_to_herror(33)
    XBDM_INVALIDCAPCFG = code_to_herror(34)
    XBDM_CAPNOTENABLED = code_to_herror(35)
    XBDM_TOOBIGJUMP = code_to_herror(36)
    XBDM_FIELDNOTPRESENT = code_to_herror(37)
    XBDM_OUTPUTBUFFERTOOSMALL = code_to_herror(38)
    XBDM_PROFILEREBOOT = code_to_herror(39)
    XBDM_MAXDURATIONEXCEEDED = code_to_herror(41)
    XBDM_INVALIDSTATE = code_to_herror(42)
    XBDM_MAXEXTENSIONS = code_to_herror(43)
    XBDM_PMCSESSIONALREADYACTIVE = code_to_herror(44)
    XBDM_PMCSESSIONNOTACTIVE = code_to_herror(45)
    XBDM_LINE_TOO_LONG = [code_to_herror(46), "line too long"]
    XBDM_D3D_DEBUG_COMMAND_NOT_IMPLEMENTED = code_to_herror(0x50)
    XBDM_D3D_INVALID_SURFACE = code_to_herror(0x51)
    #XBDM_CANNOTCONNECT = code_to_herror(0x100)
    #XBDM_CONNECTIONLOST = code_to_herror(0x101)
    #XBDM_FILEERROR = code_to_herror(0x103)
    #XBDM_ENDOFLIST = code_to_herror(0x104)
    #XBDM_BUFFER_TOO_SMALL = code_to_herror(0x105)
    #XBDM_NOTXBEFILE = code_to_herror(0x106)
    #XBDM_MEMSETINCOMPLETE = code_to_herror(0x107)
    #XBDM_NOXBOXNAME = code_to_herror(0x108)
    #XBDM_NOERRORSTRING = code_to_herror(0x109)
    #XBDM_INVALIDSTATUS = code_to_herror(0x10A)
    #XBDM_TASK_PENDING = code_to_herror(0x150)

    #success
    XBDM_NOERR = [code_to_hsuccess(0), "OK"]
    XBDM_CONNECTED = code_to_hsuccess(1)
    XBDM_MULTIRESPONSE = [code_to_hsuccess(2), "multiline response follows"]
    XBDM_BINRESPONSE = [code_to_hsuccess(3), "binary response follows"]
    XBDM_READYFORBIN = [code_to_hsuccess(4), "send binary data"]
    XBDM_DEDICATED = code_to_hsuccess(5)
    XBDM_PROFILERESTARTED = code_to_hsuccess(6)
    XBDM_FASTCAPENABLED = code_to_hsuccess(7)
    XBDM_CALLCAPENABLED = code_to_hsuccess(8)
    XBDM_RESULTCODE = code_to_hsuccess(9)

    E_OUTOFMEMORY = [0x8007000E, "out of memory"]
    E_UNEXPECTED = [0x8000FFFF, "unexpected error"]
    E_INVALIDARG = [0x80070057, "bad parameter"]

if __name__ == "__main__":
    print(hex(hresult_to_code(0x82DA0101)))