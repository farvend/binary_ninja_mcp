import importlib.util
import json
import sys
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path


class FakeType:
    width = 10_000

    def __str__(self):
        return "uint8_t [10000]"


class FakeView:
    def __init__(self):
        self.read_lengths = []

    def get_data_var_at(self, _address):
        return types.SimpleNamespace(type=FakeType())

    def read(self, _address, length):
        self.read_lengths.append(length)
        return b"A" * length


def _load_http_server_module():
    binaryninja = types.ModuleType("binaryninja")
    for level in ("debug", "info", "warn", "error"):
        setattr(binaryninja, f"log_{level}", lambda _message: None)
    settings = types.ModuleType("binaryninja.settings")
    settings.Settings = object
    sys.modules["binaryninja"] = binaryninja
    sys.modules["binaryninja.settings"] = settings

    for package in ("plugin", "plugin.server", "plugin.api", "plugin.core", "plugin.utils"):
        module = types.ModuleType(package)
        module.__path__ = []
        sys.modules[package] = module

    endpoints = types.ModuleType("plugin.api.endpoints")
    endpoints.BinaryNinjaEndpoints = object
    sys.modules[endpoints.__name__] = endpoints

    binary_operations = types.ModuleType("plugin.core.binary_operations")

    class BinaryOperations:
        def __init__(self, _config):
            self.current_view = FakeView()

        def infer_data_size(self, _address):
            return None

    binary_operations.BinaryOperations = BinaryOperations
    sys.modules[binary_operations.__name__] = binary_operations

    config = types.ModuleType("plugin.core.config")
    config.Config = object
    sys.modules[config.__name__] = config

    number_utils = types.ModuleType("plugin.utils.number_utils")
    number_utils.convert_number = lambda value, size: (value, size)
    sys.modules[number_utils.__name__] = number_utils

    string_utils = types.ModuleType("plugin.utils.string_utils")
    string_utils.parse_int_or_default = lambda value, default: (
        int(value) if value is not None else default
    )
    sys.modules[string_utils.__name__] = string_utils

    path = Path(__file__).parents[1] / "plugin" / "server" / "http_server.py"
    spec = importlib.util.spec_from_file_location("plugin.server.http_server", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ServerConfig:
    server = types.SimpleNamespace(host="127.0.0.1", port=0)
    binary_ninja = object()


class DataDeclTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _load_http_server_module()

    def setUp(self):
        self.server = self.module.MCPServer(ServerConfig())
        self.server.start()

    def tearDown(self):
        self.server.stop()

    def request(self, query=""):
        port = self.server.server.server_address[1]
        url = f"http://127.0.0.1:{port}/getDataDecl?address=0x1000{query}"
        with urllib.request.urlopen(url, timeout=2) as response:
            return json.load(response)

    def test_default_request_returns_bounded_preview(self):
        data = self.request()

        self.assertEqual(data["size"], 10_000)
        self.assertEqual(data["bytes_read"], self.module.DATA_DECL_PREVIEW_BYTES)
        self.assertTrue(data["truncated"])
        self.assertEqual(
            self.server.binary_ops.current_view.read_lengths[-1],
            self.module.DATA_DECL_PREVIEW_BYTES,
        )

    def test_explicit_length_is_honored(self):
        data = self.request("&length=16")

        self.assertEqual(data["bytes_read"], 16)
        self.assertTrue(data["truncated"])
        self.assertEqual(self.server.binary_ops.current_view.read_lengths[-1], 16)

    def test_oversized_explicit_length_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.request(f"&length={self.module.DATA_DECL_MAX_BYTES + 1}")

        with raised.exception as response:
            error = json.load(response)
        self.assertEqual(raised.exception.code, 400)
        self.assertEqual(error["max_length"], self.module.DATA_DECL_MAX_BYTES)
        self.assertEqual(self.server.binary_ops.current_view.read_lengths, [])


if __name__ == "__main__":
    unittest.main()
