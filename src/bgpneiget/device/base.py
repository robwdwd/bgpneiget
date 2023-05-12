
from typing import Type

from scrapli.driver.base import AsyncDriver


class BaseDevice:

    PROTOCOL_TRANSPORT_MAP = {
        "TELNET": 'telnet',
        "SSH": 'asyncssh',
    }


    def __init__(self, device) -> None:
        self.os = device["os"]
        self.hostname = device["hostname"]
        self.transport = self.PROTOCOL_TRANSPORT_MAP[device["protocol"]]

    def setup_device_args(self, username: str, password: str) -> dict:
        """Set up some default device arguments.

        Args:
            username (str): Username
            password (str): Password

        Returns:
            dict: Host args
        """

        return {
            "host": self.hostname,
            "auth_strict_key": False,
            "transport": self.transport,
            "auth_username": username,
            "auth_password": password,
        }

    def get_driver(self) -> Type[AsyncDriver]:
        return AsyncDriver
        