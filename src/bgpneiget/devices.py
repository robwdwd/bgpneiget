
import pprint

from bgpneiget.device.arista import EOSDevice
from bgpneiget.device.cisco import IOSDevice, IOSXRDevice
from bgpneiget.device.juniper import JunOsDevice

pp = pprint.PrettyPrinter(indent=2, width=120)

def init_device(device):
    DEVICE_TYPE_MAP = {
        "IOS": IOSDevice,
        "IOS-XR": IOSXRDevice,
        "IOS-XE": IOSDevice,
        "JunOS": JunOsDevice,
        "EOS": EOSDevice,
    }
    pp.pprint(device)
    return DEVICE_TYPE_MAP[device["os"]](device)