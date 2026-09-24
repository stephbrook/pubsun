"""Solar position. Azimuth is degrees clockwise from north; elevation is degrees above the horizon."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MEL = ZoneInfo("Australia/Melbourne")


def _julian_day(utc: datetime) -> float:
    y, m = utc.year, utc.month
    d = utc.day + (utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3.6e9) / 24
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def sun_position(when: datetime, lat: float, lon: float) -> tuple[float, float]:
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    utc = when.astimezone(timezone.utc)

    jd = _julian_day(utc)
    jc = (jd - 2451545.0) / 36525.0

    l0 = (280.46646 + jc * (36000.76983 + 0.0003032 * jc)) % 360
    m_anom = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    mr = math.radians(m_anom)
    c = (
        math.sin(mr) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + math.sin(2 * mr) * (0.019993 - 0.000101 * jc)
        + math.sin(3 * mr) * 0.000289
    )
    sun_true = l0 + c
    omega = 125.04 - 1934.136 * jc
    lamb = sun_true - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    eps0 = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))
    decl = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(lamb))))

    y = math.tan(math.radians(eps) / 2) ** 2
    l0r = math.radians(l0)
    eqtime = 4 * math.degrees(
        y * math.sin(2 * l0r)
        - 2 * e * math.sin(mr)
        + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
        - 0.5 * y * y * math.sin(4 * l0r)
        - 1.25 * e * e * math.sin(2 * mr)
    )

    minutes = utc.hour * 60 + utc.minute + utc.second / 60 + utc.microsecond / 6e7
    solar_time = (minutes + eqtime + 4 * lon) % 1440
    ha = solar_time / 4 - 180
    if ha < -180:
        ha += 360

    latr = math.radians(lat)
    declr = math.radians(decl)
    har = math.radians(ha)
    cos_zen = math.sin(latr) * math.sin(declr) + math.cos(latr) * math.cos(declr) * math.cos(har)
    zenith = math.degrees(math.acos(min(1, max(-1, cos_zen))))
    elevation = 90 - zenith

    az_denom = math.cos(latr) * math.sin(math.radians(zenith))
    if abs(az_denom) > 0.001:
        az_cos = ((math.sin(latr) * math.cos(math.radians(zenith))) - math.sin(declr)) / az_denom
        az_cos = min(1, max(-1, az_cos))
        azimuth = 180 - math.degrees(math.acos(az_cos))
        if ha > 0:
            azimuth = -azimuth
    else:
        azimuth = 180 if lat > 0 else 0
    if azimuth < 0:
        azimuth += 360

    return azimuth % 360, elevation
