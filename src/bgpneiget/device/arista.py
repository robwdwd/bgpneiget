
from typing import Type

from scrapli.driver.core import AsyncEOSDriver

from bgpneiget.device.base import BaseDevice


class EOSDevice(BaseDevice):

    def get_driver(self)-> Type[AsyncEOSDriver]:
        return AsyncEOSDriver