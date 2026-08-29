from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class GpsStatus(IntEnum):
    """Quality of the vehicle's last GPS fix (ASN.1 ``GPSStatus``)."""

    NO_SIGNAL = 0
    TIME_FIX = 1
    FIX_2D = 2
    FIX_3D = 3


@dataclass(slots=True)
class GpsPosition:
    """A decoded ``RvsPosition``, in ordinary units.

    Latitude and longitude are degrees (the protocol carries micro-degrees) and
    altitude is metres. Speed is
    km/h from the protocol's tenths.
    ``hdop`` is left in raw protocol units because the scale the
    vehicle uses is not confirmed either.
    """

    latitude: float | None = None
    longitude: float | None = None
    altitude_m: int | None = None
    heading_deg: int | None = None
    speed_kmh: float | None = None
    hdop: int | None = None
    satellites: int | None = None
    gps_status: GpsStatus | None = None
    position_time: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def has_fix(self) -> bool:
        """True when the vehicle reported a usable 2D or 3D fix."""
        return (
            self.gps_status in (GpsStatus.FIX_2D, GpsStatus.FIX_3D)
            and self.latitude is not None
            and self.longitude is not None
        )


@dataclass(frozen=True, slots=True)
class SubaccountGrant:
    """One car-sharing grant from the ``userVinList`` entry.

    On a **secondary** account, the entry's ``subaccountInfo`` object is this
    account's own grant (parsed into :attr:`Vehicle.subaccount_grant`). On the
    **primary** account, the entry's ``subaccountList`` holds one of these per
    account the owner has shared the car with (parsed into
    :attr:`Vehicle.subaccounts`). Fields are copied verbatim from the API;
    :attr:`raw` keeps the whole object for anything not surfaced here.
    """

    subaccount_id: int | None = None
    subscriber_id: int | None = None
    authorized_subscriber_id: int | None = None
    user_name: str | None = None
    """Display name on the grant (the shared-with user, PII)."""
    user_account: str | None = None
    """Account identifier on the grant, e.g. a phone number (PII)."""
    authorization_card_type: int | None = None
    """Permission tier of the grant; code meanings unconfirmed."""
    location_authorization: int | None = None
    """Whether the grant includes location access (1 = yes in captures)."""
    validity_start_time: int | None = None
    """Grant validity start, Unix epoch seconds."""
    validity_end_time: int | None = None
    """Grant validity end, Unix epoch seconds; 0 = open-ended in captures."""
    operation_type: int | None = None
    status: int | None = None
    create_date: int | None = None
    """Grant creation time, Unix epoch milliseconds."""
    vin: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    """The full ``subaccountInfo``/``subaccountList`` object as returned, for
    fields not surfaced as attributes above."""


@dataclass(slots=True)
class Vehicle:
    vin: str
    name: str
    brand: str | None = None
    model: str | None = None
    """Human-readable model name, e.g. "Windsor"."""
    model_year: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    color_name: str | None = None
    """Exterior colour as reported by the API, e.g. "Clay Beige"."""
    series: str | None = None
    """Raw API model/series code (e.g. "EQ100"), needed for per-model asset lookups (images, CDN paths). Distinct from :attr:`model`."""
    is_subaccount: bool | None = None
    """Whether **this** account is a secondary (granted-access) account for this
    vehicle.

    ``False`` on the primary/owner account (the one the car was first bound to);
    ``True`` on a secondary account the owner has shared the car with. ``None``
    when the API did not report it. Decoded from the ``isSubaccount`` flag the
    ``userVinList`` entry carries, which is the reliable primary-vs-secondary
    discriminator (a secondary entry additionally carries a ``subaccountInfo``
    grant object; a primary entry carries a ``subaccountList``). Use
    :attr:`is_primary_account` for the inverse."""
    is_current_vehicle: bool | None = None
    """Whether the API marks this as the account's currently-selected vehicle
    (``isCurrentVehicle``)."""
    is_activated: bool | None = None
    """Whether the vehicle is activated on this account (``isActivate``)."""
    bind_time: int | None = None
    """When the vehicle was bound to this account, Unix epoch **milliseconds**
    (``bindTime``). Differs per account: the owner's is the original binding, a
    secondary's is when access was granted."""
    tbox_sim_no: str | None = None
    """T-Box embedded-SIM number (``tboxSimNo``); telemetry SIM, not the user's
    phone."""
    subaccount_grant: SubaccountGrant | None = None
    """This account's own grant, present only on a **secondary** account
    (``subaccountInfo``); ``None`` on the owner account."""
    subaccounts: list[SubaccountGrant] = field(default_factory=list)
    """Accounts the owner has shared this car with, present only on the
    **primary** account (``subaccountList``); empty on a secondary account and
    when nothing has been shared."""

    @property
    def is_primary_account(self) -> bool | None:
        """``True`` on the owner account, ``False`` on a secondary account.

        The inverse of :attr:`is_subaccount`; ``None`` when the role is unknown.
        """
        return None if self.is_subaccount is None else not self.is_subaccount


@dataclass(slots=True)
class Capabilities:
    climate: bool = False
    door_lock: bool = False
    find_my_car: bool = False
    tailgate: bool = False
    sunroof: bool = False
    heated_seats: bool = False
    window_param_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class Status:
    """Vehicle state from one TAP poll.

    Primarily the decoded 195-byte full-status frame, with two satellites the
    same poll can carry: :attr:`gps` and :attr:`charge`.
    """

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
    gps: GpsPosition | None = None
    charge: ChargeStatus | None = None
    """EV charging status collected from the same poll, or ``None``.

    The 195-byte full-status frame and the 63-byte charging frame ride the same
    TAP poll stream, interleaved, so one poll can yield both — sparing a caller
    that needs both each refresh a second, redundant poll of the same endpoint.
    :meth:`~mg_ismart_india_client.client.MgIndiaClient.status` waits for the
    charging frame only when asked (``include_charge=True``), but attaches one
    that happens to arrive either way.

    ``None`` is a routine outcome, not an error: a non-EV, ``include_charge``
    left off, a poll budget that expired before a charging frame arrived, or a
    secondary account whose charging telemetry is disabled server-side.

    Carries its own :attr:`ChargeStatus.status_time`, which the vehicle produces
    independently of :attr:`status_time` here; the two may differ.
    """


@dataclass(slots=True)
class Snapshot:
    vehicle: Vehicle
    capabilities: Capabilities
    status: Status
    user_info: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ChargeStatus:
    """Decoded EV charging status (the app-id 511 charging frame).

    Produced by :func:`~mg_ismart_india_client.tap.decode_charge_status` and
    returned by :meth:`~mg_ismart_india_client.client.MgIndiaClient.charge_status`.

    Every field the frame carries is exposed here. Those whose scale is confirmed
    (against captured frames spanning roughly 4-18 A charge current and 45-100%
    SOC) are given in real units and named for that unit; those still unconfirmed
    keep the vehicle's own integer and carry a ``_raw`` suffix, so no attribute ever
    implies a precision the decoder cannot back up. Attributes typed ``| None`` are
    the ones the protocol marks OPTIONAL and the vehicle may omit.
    """

    is_charging: bool
    """True while the pack is actively charging."""
    is_plugged_in: bool
    """True whenever the charge gun is connected (whether charging or not)."""
    charging_type: int
    """Charge-type code from the frame; observed 2 while charging, 5/6 when idle or
    complete. Full code table unconfirmed."""
    charging_electricity_phase: int | None
    """Supply phase code; code meanings unconfirmed."""

    soc: float | None
    """State of charge, percent (0-100); ``None`` if the frame omits it."""
    range_km: float
    """Estimated electric range, kilometres."""

    charging_voltage: float
    """Charging (pack) voltage, volts."""
    charging_current: float
    """Charging current, amperes; ~0 A when idle, so gate on :attr:`is_charging`."""
    battery_energy_kwh: float
    """Energy currently in the pack, kilowatt-hours. Decoded from the frame's
    ``realtimePower`` field x 0.1 despite the field's misleading name. Empirically
    SOC x usable capacity: energy / SOC holds at ~37 kWh across every captured
    frame from 45% to 100% SOC."""
    working_voltage: float | None
    """Pack voltage, volts, at coarser (2.5 V) resolution than
    :attr:`charging_voltage`; mirrors it in every captured frame."""
    working_current: float | None
    """Working current, amperes; identical to :attr:`charging_current` in every
    captured frame (same encoding)."""

    charge_time_elapsed_s: int | None
    """Elapsed time in the current charge session, seconds; ``None`` if absent."""
    start_time: int | None
    """Charge-session start, Unix epoch seconds; ``None`` when not charging."""
    end_time: int | None
    """Estimated charge-session end, Unix epoch seconds; ``None`` when not
    charging."""
    charging_time_level_prc_raw: int | None
    """Time-to-target field, raw. Counts down while charging; ``None`` here when
    the frame sends its 0xFFFF idle sentinel. Unit/rate unconfirmed."""

    charging_pile_id: str | None
    """Identifier of the charge point, when the vehicle reports one."""
    charging_pile_supplier: str | None
    """Operator of the charge point, when the vehicle reports one."""

    odometer_km: float
    """Total distance travelled, kilometres."""
    distance_since_last_charge_km: float | None
    """Distance driven since the last charge, kilometres (raw x 0.1); resets to 0
    at full."""
    power_usage_since_last_charge_raw: int | None
    """Energy used since the last charge, in **raw units** (scale unconfirmed;
    varies inversely with SOC across captures)."""
    mileage_of_day_raw: int | None
    """Distance travelled today, in **raw protocol units** (scale unconfirmed)."""
    power_usage_of_day_raw: int | None
    """Energy used today, in **raw protocol units** (scale unconfirmed)."""
    static_energy_consumption_raw: int | None
    """Static energy consumption, in **raw protocol units** (scale unconfirmed)."""

    total_battery_capacity_kwh: float | None
    """Total pack capacity, kilowatt-hours (raw x 0.1); absent in captured frames,
    but the scale matches the global SAIC schema for this field."""
    last_charge_energy_kwh: float | None
    """Pack energy at the end of the last charge, kilowatt-hours (raw x 0.1);
    mirrors :attr:`battery_energy_kwh` in every captured frame."""
    fota_lowest_voltage_raw: int | None
    """Lowest cell voltage reported for FOTA, in **raw units** (unconfirmed)."""

    status_time: int
    """Time this frame was produced, Unix epoch seconds."""
    extended_data_1: int | None = None
    """Opaque vendor extension field; contents undocumented."""
    extended_data_2: int | None = None
    """Opaque vendor extension field; contents undocumented."""
    extended_data_3: str | None = None
    """Opaque vendor extension field; contents undocumented."""
    extended_data_4: str | None = None
    """Opaque vendor extension field; contents undocumented."""
    _raw: dict[str, Any] = field(default_factory=dict)
    """Full decoded ``RvsChargingStatus``, in raw protocol units.

    Private: kept for debugging and protocol work only. Every field it holds is
    exposed as a documented attribute above, so consumers should use those instead
    — the shape and contents of this dict are not part of the public API and may
    change with the protocol schema at any time.
    """
