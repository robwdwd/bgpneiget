from typing import Type

from scrapli.driver.core import AsyncJunosDriver

from bgpneiget.device.base import BaseDevice


class JunOsDevice(BaseDevice):
    def bgp_sum_cmd(self) -> str:
        return "show bgp sum"

    def get_driver(self) -> Type[AsyncJunosDriver]:
        return AsyncJunosDriver
