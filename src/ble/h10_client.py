"""Polar H10 BLE client for heart rate and RR interval acquisition."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Awaitable
from bleak import BleakClient
from bleak.backends.device import BLEDevice

from .parser import parse_heart_rate_measurement, HeartRateData


# Standard Bluetooth Heart Rate Service UUIDs
HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_CHAR_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

# Battery Service
BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHAR_UUID = "00002a19-0000-1000-8000-00805f9b34fb"


@dataclass
class H10Status:
    """Current status of H10 connection."""
    connected: bool = False
    device_name: str | None = None
    device_address: str | None = None
    battery_level: int | None = None
    sensor_contact: bool = False
    last_hr: int | None = None
    last_rr: list[int] = field(default_factory=list)
    packets_received: int = 0


# Type alias for data callback
DataCallback = Callable[[HeartRateData, datetime], Awaitable[None] | None]


class H10Client:
    """Client for connecting to and receiving data from Polar H10."""

    def __init__(self, device: BLEDevice | str):
        """Initialize with BLEDevice or address string."""
        self._device = device
        self._client: BleakClient | None = None
        self._callbacks: list[DataCallback] = []
        self._status = H10Status()
        self._running = False

    @property
    def status(self) -> H10Status:
        return self._status

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    def on_data(self, callback: DataCallback):
        """Register a callback for heart rate data."""
        self._callbacks.append(callback)

    async def connect(self) -> bool:
        """Connect to the H10 device."""
        try:
            self._client = BleakClient(self._device)
            await self._client.connect()

            if self._client.is_connected:
                self._status.connected = True

                # Get device info
                if hasattr(self._device, 'name'):
                    self._status.device_name = self._device.name
                if hasattr(self._device, 'address'):
                    self._status.device_address = self._device.address
                elif isinstance(self._device, str):
                    self._status.device_address = self._device

                # Try to read battery level
                try:
                    battery = await self._client.read_gatt_char(BATTERY_LEVEL_CHAR_UUID)
                    self._status.battery_level = battery[0]
                except Exception:
                    pass  # Battery service may not be available

                return True
        except Exception as e:
            print(f"Connection failed: {e}")
            self._status.connected = False

        return False

    async def disconnect(self):
        """Disconnect from the H10 device."""
        self._running = False
        if self._client and self._client.is_connected:
            await self._client.stop_notify(HEART_RATE_MEASUREMENT_CHAR_UUID)
            await self._client.disconnect()
        self._status.connected = False

    async def start_streaming(self):
        """Start receiving heart rate data."""
        if not self.is_connected:
            raise RuntimeError("Not connected to device")

        self._running = True

        def notification_handler(sender, data: bytearray):
            timestamp = datetime.now()
            hr_data = parse_heart_rate_measurement(data)

            # Update status
            self._status.sensor_contact = hr_data.sensor_contact
            self._status.last_hr = hr_data.heart_rate
            self._status.last_rr = hr_data.rr_intervals
            self._status.packets_received += 1

            # Notify callbacks
            for callback in self._callbacks:
                result = callback(hr_data, timestamp)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)

        await self._client.start_notify(
            HEART_RATE_MEASUREMENT_CHAR_UUID,
            notification_handler
        )

    async def run(self):
        """Run the client, maintaining connection."""
        while self._running:
            await asyncio.sleep(1)
            # Could add reconnection logic here


if __name__ == "__main__":
    from .scanner import scan_for_polar_h10

    async def main():
        # Find H10
        devices = await scan_for_polar_h10(timeout=10)
        if not devices:
            print("No Polar H10 found")
            return

        device = devices[0]
        print(f"\nConnecting to {device.name}...")

        client = H10Client(device)

        def on_hr_data(data: HeartRateData, timestamp: datetime):
            print(f"[{timestamp.strftime('%H:%M:%S.%f')[:-3]}] "
                  f"HR: {data.heart_rate} BPM | "
                  f"RR: {data.rr_intervals} ms | "
                  f"Contact: {data.sensor_contact}")

        client.on_data(on_hr_data)

        if await client.connect():
            print(f"Connected! Battery: {client.status.battery_level}%")
            await client.start_streaming()

            try:
                await asyncio.sleep(30)  # Stream for 30 seconds
            except KeyboardInterrupt:
                pass
            finally:
                await client.disconnect()
                print(f"\nReceived {client.status.packets_received} packets")
        else:
            print("Failed to connect")

    asyncio.run(main())
