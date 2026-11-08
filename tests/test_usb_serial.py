"""ti84.usb and ti84.serial, run against a fake usbdrvce/srldrvce and a fake link port.

The real libraries need a calculator and a cable; the fakes check that the program
calls them with the C calling convention, handles their events, and cleans up.

Run with:  python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from asm_sim import Sim

from ti84asm.compiler import Compiler

CONNECTED, ENABLED, DISCONNECTED, HOST_CONFIGURE = 2, 4, 1, 12
DEVICE_ROLE = 16


class FakeUsb:
    """A stand-in for usbdrvce and srldrvce, as LibLoad would link them."""

    def __init__(self, role=0, devices=None, rx=b""):
        self.role = role
        self.devices = devices or {}          # handle -> (vendor, product, address)
        self.enabled: list[int] = []
        self.queue: list[tuple[int, int]] = []
        self.rx = list(rx)
        self.tx = bytearray()
        self.calls: list[str] = []
        self.handler = None
        self.srl_dev = None

    @staticmethod
    def arg(sim, index):
        return sim.read(sim.sp + 3 * index, 3)

    def hooks(self):
        names = {name[4:]: getattr(self, name) for name in dir(self) if name.startswith("lib_")}

        def wrap(name, function):
            def hook(sim):
                self.calls.append(name)
                result = function(sim)
                if result is not None:
                    sim.r["hl"] = result & 0xFFFFFF
                    sim.a = result & 0xFF
            return hook
        hooks = {f"_lib_{name}": wrap(name, function) for name, function in names.items()}
        hooks["_rt_libload"] = lambda sim: self.calls.append("libload")
        return hooks

    def plug(self, handle):
        self.queue.append((CONNECTED, handle))

    def lib_usb_Init(self, sim):
        self.handler = self.arg(sim, 0)
        self.descriptors = self.arg(sim, 2)
        return 0

    def lib_usb_Cleanup(self, sim):
        return None

    def lib_usb_HandleEvents(self, sim):
        while self.queue:
            event, data = self.queue.pop(0)
            if event == ENABLED:
                self.enabled.append(data)
            result = sim.call(self.handler, [event, data, 0])
            assert result == 0, f"handler returned {result} for event {event}"
        return 0

    def lib_usb_GetRole(self, sim):
        return self.role

    def lib_usb_ResetDevice(self, sim):
        self.queue.append((ENABLED, self.arg(sim, 0)))
        return 0

    def lib_usb_FindDevice(self, sim):
        after, ready = self.arg(sim, 1), sorted(self.enabled)
        later = [handle for handle in ready if handle > after] if after else ready
        return later[0] if later else 0

    def lib_usb_GetDescriptor(self, sim):
        device, buffer, length = self.arg(sim, 0), self.arg(sim, 3), self.arg(sim, 4)
        vendor, product, _ = self.devices[device]
        descriptor = bytes([18, 1, 0, 2, 0, 0, 0, 64]) + vendor.to_bytes(2, "little") + \
            product.to_bytes(2, "little") + bytes(6)
        for offset, value in enumerate(descriptor[:length]):
            sim.write(buffer + offset, value)
        sim.write(self.arg(sim, 5), min(length, 18), 3)
        return 0

    def lib_usb_GetDeviceAddress(self, sim):
        return self.devices[self.arg(sim, 0)][2]

    def lib_srl_GetCDCStandardDescriptors(self, sim):
        return 0xCDC000

    def lib_srl_UsbEventCallback(self, sim):
        return 0

    def lib_srl_Open(self, sim):
        self.srl_dev = self.arg(sim, 1)
        sim.write(self.arg(sim, 0), self.srl_dev, 3)
        self.baud = self.arg(sim, 5)
        return 0

    def lib_srl_Close(self, sim):
        self.srl_dev = None
        return None

    def lib_srl_Read(self, sim):
        if not self.rx:
            return 0
        sim.write(self.arg(sim, 1), self.rx.pop(0))
        return 1

    def lib_srl_Write(self, sim):
        start, length = self.arg(sim, 1), self.arg(sim, 2)
        self.tx += bytes(sim.read(start + i) for i in range(length))
        return length


def run(source, target="ce", usb=None, **kwargs):
    compiler = Compiler("T", target)
    hooks = usb.hooks() if usb else {}
    sim = Sim(compiler.compile(source), target, hooks=hooks, **kwargs)
    sim.run(5_000_000)
    return sim, compiler


def value(sim, compiler, name):
    return sim.word(compiler.variables[name])


class UsbTests(unittest.TestCase):
    def test_libload_runs_first_and_the_driver_stops_on_exit(self):
        usb = FakeUsb()
        run("from ti84 import usb\nz = usb.begin()\n", usb=usb)
        self.assertEqual(usb.calls[0], "libload")
        self.assertEqual(usb.calls[-1], "usb_Cleanup")
        self.assertEqual(usb.descriptors, 0)

    def test_a_plugged_device_is_reset_found_and_identified(self):
        usb = FakeUsb(devices={0xD40000: (0x046D, 0xC31C, 3)})
        usb.plug(0xD40000)
        source = ("from ti84 import usb\nusb.begin()\nz = usb.poll()\nd = usb.find()\nv = usb.vendor_id(d)\n"
                  "p = usb.product_id(d)\na = usb.address(d)\nn = usb.find(d)\nc = usb.connected()\n"
                  "e = usb.last_event()\n")
        sim, compiler = run(source, usb=usb)
        got = {name: value(sim, compiler, name) for name in "zdvpance"}
        self.assertEqual(got, {"z": 0, "d": 0xD40000 - (1 << 24), "v": 0x046D, "p": 0xC31C, "a": 3, "n": 0,
                               "c": 1, "e": ENABLED})
        self.assertIn("usb_ResetDevice", usb.calls)

    def test_not_started_polls_minus_one(self):
        sim, compiler = run("from ti84 import usb\nz = usb.poll()\n", usb=FakeUsb())
        self.assertEqual(value(sim, compiler, "z"), -1)


class SerialCeTests(unittest.TestCase):
    def test_echo_through_a_usb_serial_device(self):
        usb = FakeUsb(rx=b"AB")
        usb.plug(0xD50000)
        source = ("from ti84 import serial\nserial.begin(115200)\nok = serial.connected()\n"
                  "a = serial.read_byte()\nb = serial.read_byte()\nc = serial.read_byte()\n"
                  "serial.write_byte(a)\nn = serial.write('Hi!')\nm = serial.write_int(-42)\n")
        sim, compiler = run(source, usb=usb)
        got = {name: value(sim, compiler, name) for name in ("ok", "a", "b", "c", "n", "m")}
        self.assertEqual(got, {"ok": 1, "a": 65, "b": 66, "c": -1, "n": 3, "m": 3})
        self.assertEqual(bytes(usb.tx), b"AHi!-42")
        self.assertEqual(usb.baud, 115200)
        self.assertEqual(usb.descriptors, 0xCDC000)
        # srl_Open runs outside the event handler, and the port is closed before cleanup.
        self.assertLess(usb.calls.index("usb_HandleEvents"), usb.calls.index("srl_Open"))
        self.assertLess(usb.calls.index("srl_Close"), usb.calls.index("usb_Cleanup"))

    def test_a_computer_host_configures_the_calculator(self):
        usb = FakeUsb(role=DEVICE_ROLE)
        usb.enabled.append(0xD60000)
        usb.queue.append((HOST_CONFIGURE, 0))
        sim, compiler = run("from ti84 import serial\nserial.begin()\nok = serial.connected()\n", usb=usb)
        self.assertEqual(value(sim, compiler, "ok"), 1)
        self.assertEqual(usb.srl_dev, None)          # closed again on exit
        self.assertNotIn("usb_ResetDevice", usb.calls)

    def test_unplugging_closes_the_port(self):
        usb = FakeUsb()
        usb.plug(0xD50000)
        source = ("from ti84 import serial\nserial.begin()\na = serial.connected()\n"
                  "b = serial.connected()\nc = serial.write_byte(1)\n")
        compiler = Compiler("T", "ce")
        hooks = usb.hooks()
        original = hooks["_lib_usb_HandleEvents"]
        polls = []

        def handle(sim):
            polls.append(1)
            if len(polls) == 2:
                usb.queue.append((DISCONNECTED, 0xD50000))
            original(sim)
        hooks["_lib_usb_HandleEvents"] = handle
        sim = Sim(compiler.compile(source), "ce", hooks=hooks)
        sim.run(5_000_000)
        self.assertEqual([value(sim, compiler, n) for n in "abc"], [1, 0, 0])


class SerialClassicTests(unittest.TestCase):
    def test_bytes_go_over_the_link_port(self):
        sim = Sim(Compiler("T", "classic").compile(
            "from ti84 import serial\nserial.begin()\nserial.write('OK')\nserial.write_int(12)\n"
            "a = serial.read_byte()\nb = serial.read_byte()\n"), "classic")
        sim.link_in = [7]
        sim.run(3_000_000)
        self.assertEqual(bytes(sim.link_out), b"OK12")
        self.assertEqual((sim.word("var_0"), sim.word("var_1")), (7, -1))

    def test_no_partner_is_a_failure_not_err_link(self):
        compiler = Compiler("T", "classic")
        sim = Sim(compiler.compile("from ti84 import serial\nok = serial.write_byte(5)\nn = serial.write('AB')\n"),
                  "classic")
        sim.link_connected = False
        sim.run(3_000_000)
        self.assertEqual((value(sim, compiler, "ok"), value(sim, compiler, "n")), (0, 0))
        self.assertEqual(sim.exit_sp, sim.sp_start)


class SaxExampleTests(unittest.TestCase):
    """examples/sax, the SAX chat client, against the fake USB serial bridge."""

    def run_sax(self, keys, rx=b"", config=None):
        from ti84asm.project import load_sources

        source, _ = load_sources(Path(__file__).resolve().parents[1] / "examples/sax/src/main.py")
        compiler = Compiler("SAXCE", "ce", source_dir=Path(__file__).resolve().parents[1] / "examples/sax/src")
        usb = FakeUsb(rx=rx)
        usb.plug(0xD50000)
        appvars = {"SAXCFG": config} if config is not None else {}
        sim = Sim(compiler.compile(source), "ce", keys=list(keys), hooks=usb.hooks(), appvars=appvars)
        sim.run(150_000_000)
        return sim, compiler, usb

    def test_chats_with_the_bridge(self):
        rx = b"R\nM bob\thi there\nS Joined #cemetech\n"
        # Two idle loops, then type h (^) and i (x^2), send with enter, and quit with clear.
        sim, compiler, usb = self.run_sax([0, 0, 14, 45, 9, 0, 15], rx, b"Akhil\0\0")
        self.assertEqual(bytes(usb.tx), b"H Akhil\nH Akhil\nM hi\n")
        self.assertEqual(usb.baud, 115200)
        log = compiler.array_labels
        count = sim.word(compiler.variables["log_count"])
        kinds = [sim.read(sim.labels[log["log_kind"]] + 3 * i, 3) for i in range(count)]
        # Welcome, plug in, linked, bob's message, the status line, and our echo.
        self.assertEqual(kinds, [ord("S"), ord("S"), ord("S"), ord("M"), ord("S"), ord("E")])
        who = [sim.read(sim.labels[log["log_who"]] + 3 * (3 * 15 + i), 3) for i in range(3)]
        self.assertEqual(bytes(who), b"bob")
        self.assertEqual(usb.calls[-1], "usb_Cleanup")

    def test_first_run_asks_for_a_nickname_and_saves_it(self):
        # No SAXCFG: type "ab" at the prompt, save with enter, then quit.
        sim, compiler, usb = self.run_sax([47, 39, 9, 0, 15])
        self.assertEqual(sim.appvar("SAXCFG")[:4], b"ab\0\0")
        self.assertIn(b"H ab\n", bytes(usb.tx))

    def test_cancelling_the_first_nickname_quits(self):
        sim, compiler, usb = self.run_sax([15])
        self.assertEqual(bytes(usb.tx), b"")
        self.assertEqual(usb.calls[-1], "usb_Cleanup")


if __name__ == "__main__":
    unittest.main()
