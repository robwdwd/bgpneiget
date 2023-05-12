from typing import Type

from scrapli.driver.core import AsyncIOSXEDriver, AsyncIOSXRDriver

from bgpneiget.device.base import BaseDevice


class IOSDevice(BaseDevice):
    def bgp_sum_cmd(self) -> str:
        return "show ip bgp sum"

    def get_driver(self)-> Type[AsyncIOSXEDriver]:
        return AsyncIOSXEDriver


class IOSXRDevice(BaseDevice):

    def bgp_sum_cmd(self) -> str:
        return "show bgp sum"

    def get_driver(self) -> Type[AsyncIOSXRDriver]:
        return AsyncIOSXRDriver
