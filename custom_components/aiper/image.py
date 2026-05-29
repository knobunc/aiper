"""Image platform for Aiper IrriSense."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import IrriSenseCoordinator
from .entity import IrriSenseEntity
from .map_render import render_map
from .number import CONF_MAP_ROTATION

type AiperConfigEntry = ConfigEntry[IrriSenseCoordinator]

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AiperConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([IrriSenseMapImage(hass, coordinator)])


class IrriSenseMapImage(IrriSenseEntity, ImageEntity):
    """Image entity that renders the irrigation zone map."""

    _attr_content_type = "image/png"
    _attr_translation_key = "map"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: IrriSenseCoordinator,
    ) -> None:
        IrriSenseEntity.__init__(self, coordinator)
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{coordinator.address}-map"

    def image(self) -> bytes | None:
        state = self.coordinator.data
        if not state.zones or not any(z.points for z in state.zones):
            return None
        rotation = float(
            self.coordinator.config_entry.options.get(
                CONF_MAP_ROTATION, 0
            )
        )
        position: tuple[int, int] | None = None
        if (
            state.is_irrigating
            and state.position_x is not None
            and state.position_y is not None
        ):
            position = (state.position_x, state.position_y)
        return render_map(state.zones, position, rotation)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()
