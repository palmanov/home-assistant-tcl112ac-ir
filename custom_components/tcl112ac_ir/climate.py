"""Climate platform for a TCL112AC air conditioner controlled over IR."""

from __future__ import annotations

import json
from typing import Any

import voluptuous as vol

from homeassistant.components.climate import PLATFORM_SCHEMA, ClimateEntity
from homeassistant.components.climate.const import ClimateEntityFeature, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, CONF_NAME, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .ir import FANS, SWINGS, generate_code

CONF_MQTT_TOPIC = "mqtt_topic"
DEFAULT_NAME = "TCL112AC Climate"
DEFAULT_MQTT_TOPIC = "zigbee2mqtt/UFO-R11/set"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_MQTT_TOPIC, default=DEFAULT_MQTT_TOPIC): cv.string,
    }
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Set up the TCL112AC climate entity from YAML."""
    async_add_entities([Tcl112AcClimate(config[CONF_NAME], config[CONF_MQTT_TOPIC])])


class Tcl112AcClimate(RestoreEntity, ClimateEntity):
    """Optimistic climate entity backed by a Zigbee IR transmitter."""

    _attr_should_poll = False
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 16
    _attr_max_temp = 31
    _attr_precision = 1.0
    _attr_target_temperature_step = 1.0
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_fan_modes = list(FANS)
    _attr_swing_modes = list(SWINGS)
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, name: str, mqtt_topic: str) -> None:
        self._attr_name = name
        self._attr_unique_id = "tcl112ac_ir_climate"
        self._mqtt_topic = mqtt_topic
        self._attr_hvac_mode = HVACMode.OFF
        self._last_active_mode = HVACMode.COOL
        self._attr_target_temperature = 24
        self._attr_fan_mode = "auto"
        self._attr_swing_mode = "off"

    async def async_added_to_hass(self) -> None:
        """Restore the last optimistic state after a restart."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is None:
            return

        if state.state in self.hvac_modes:
            self._attr_hvac_mode = HVACMode(state.state)
            if self._attr_hvac_mode != HVACMode.OFF:
                self._last_active_mode = self._attr_hvac_mode

        temperature = state.attributes.get(ATTR_TEMPERATURE)
        if temperature is not None:
            self._attr_target_temperature = min(31, max(16, round(float(temperature))))

        fan_mode = state.attributes.get("fan_mode")
        if fan_mode in self.fan_modes:
            self._attr_fan_mode = fan_mode

        swing_mode = state.attributes.get("swing_mode")
        if swing_mode in self.swing_modes:
            self._attr_swing_mode = swing_mode

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set operation mode and transmit the complete state."""
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.OFF:
            self._last_active_mode = hvac_mode
        await self._async_transmit()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature and transmit the complete state."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        self._attr_target_temperature = min(31, max(16, round(float(temperature))))
        await self._async_transmit()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan speed and transmit the complete state."""
        self._attr_fan_mode = fan_mode
        await self._async_transmit()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set vertical swing and transmit the complete state."""
        self._attr_swing_mode = swing_mode
        await self._async_transmit()

    async def async_turn_on(self) -> None:
        """Turn on using the most recent active mode."""
        await self.async_set_hvac_mode(self._last_active_mode)

    async def async_turn_off(self) -> None:
        """Turn the air conditioner off."""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def _async_transmit(self) -> None:
        mode = self._last_active_mode if self.hvac_mode == HVACMode.OFF else self.hvac_mode
        code = generate_code(
            power=self.hvac_mode != HVACMode.OFF,
            mode=mode,
            temperature=self.target_temperature,
            fan=self.fan_mode,
            swing=self.swing_mode,
        )
        await self.hass.services.async_call(
            "mqtt",
            "publish",
            {
                "topic": self._mqtt_topic,
                "payload": json.dumps({"ir_code_to_send": code}, separators=(",", ":")),
            },
            blocking=True,
        )
        self.async_write_ha_state()
