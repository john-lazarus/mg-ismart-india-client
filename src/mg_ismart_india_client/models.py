from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Vehicle:
    vin: str
    name: str
    brand: str | None = None
    model: str | None = None
    model_year: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Capabilities:
    climate: bool = False
    door_lock: bool = False
    find_my_car: bool = False
    tailgate: bool = False
    sunroof: bool = False
    heated_seats: bool = False
    window_param_ids: tuple[int, ...] = ()


@dataclass(slots=True)
class Status:
    status_time: int | None = None
    locked: bool | None = None
    driver_door_open: bool | None = None
    passenger_door_open: bool | None = None
    rear_left_door_open: bool | None = None
    rear_right_door_open: bool | None = None
    boot_open: bool | None = None
    bonnet_open: bool | None = None
    driver_window_open: bool | None = None
    passenger_window_open: bool | None = None
    rear_left_window_open: bool | None = None
    rear_right_window_open: bool | None = None
    sunroof_open: bool | None = None
    climate_running: bool | None = None
    interior_temperature: float | None = None
    exterior_temperature: float | None = None
    fuel_level: int | None = None
    range_km: int | None = None
    odometer_km: int | None = None
    aux_battery_voltage: float | None = None
    front_left_tyre_psi: float | None = None
    front_right_tyre_psi: float | None = None
    rear_left_tyre_psi: float | None = None
    rear_right_tyre_psi: float | None = None
    tyre_monitor_status: int | None = None
    can_bus_active: bool | None = None
    last_can_activity: int | None = None
    handbrake: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Snapshot:
    vehicle: Vehicle
    capabilities: Capabilities
    status: Status
    user_info: dict[str, Any] = field(default_factory=dict)
