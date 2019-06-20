import urllib.parse
import async_timeout
import aiohttp
import asyncio
import logging
import voluptuous as vol
import homeassistant.util as util

from datetime import timedelta
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

VERSION = '0.0.1'

DOMAIN = "samsung_multi_room"

MIN_TIME_BETWEEN_SCANS = timedelta(seconds=10)
MIN_TIME_BETWEEN_FORCED_SCANS = timedelta(seconds=3)

from homeassistant.helpers import config_validation as cv

from homeassistant.components.media_player import (
  MediaPlayerDevice,
  PLATFORM_SCHEMA
)

from homeassistant.components.media_player.const import (
  MEDIA_TYPE_CHANNEL,
  SUPPORT_TURN_ON,
  SUPPORT_TURN_OFF,
  SUPPORT_VOLUME_MUTE,
  SUPPORT_SELECT_SOURCE,
  SUPPORT_VOLUME_SET,
)

from homeassistant.const import (
  CONF_NAME,
  CONF_HOST,
  STATE_IDLE,
  STATE_PLAYING,
  STATE_OFF
)

MULTI_ROOM_SOURCE_TYPE = [
  'optical',
  'soundshare',
  'hdmi',
  'wifi',
  'aux',
  'bt',
  #wifi - submode: dlna, cp
]

DEFAULT_NAME = 'Samsung Soundbar'
BOOL_OFF = 'off'
BOOL_ON = 'on'
TIMEOUT = 10
SUPPORT_SAMSUNG_MULTI_ROOM = SUPPORT_VOLUME_SET | SUPPORT_VOLUME_MUTE | SUPPORT_SELECT_SOURCE | SUPPORT_TURN_OFF | SUPPORT_TURN_ON

CONF_MAX_VOLUME = 'max_volume'
CONF_PORT = 'port'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
  vol.Required(CONF_HOST, default='127.0.0.1'): cv.string,
  vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
  vol.Optional(CONF_PORT, default='55001'): cv.string,
  vol.Optional(CONF_MAX_VOLUME, default='100'): cv.string
})

class MultiRoomApi():
  def __init__(self, ip, port, session, hass):
    self.session = session
    self.hass = hass
    self.ip = ip
    self.port = port
    self.endpoint = 'http://{0}:{1}'.format(ip, port)

  async def _exec_cmd(self, mode ,cmd, key_to_extract):
    import xmltodict
    query = urllib.parse.urlencode({ "cmd": cmd }, quote_via=urllib.parse.quote)
    if mode == 'UIC':
      url = '{0}/UIC?{1}'.format(self.endpoint, query)
    elif mode == 'CPM':
      url = '{0}/CPM?{1}'.format(self.endpoint, query)

    try:
      with async_timeout.timeout(TIMEOUT, loop=self.hass.loop):
        _LOGGER.debug("Executing: {} with cmd: {}".format(url, cmd))
        response = await self.session.get(url)
        data = await response.text()
        _LOGGER.debug(data)
        response = xmltodict.parse(data)
        if mode == 'UIC':
          if key_to_extract in response['UIC']['response']:
            return response['UIC']['response'][key_to_extract]
          else:
            return None
        elif mode == 'CPM':
          if key_to_extract in response['CPM']['response']:
            return response['CPM']['response'][key_to_extract]
          else:
            return None
    except (asyncio.TimeoutError, ValueError):
      _LOGGER.debug("Timeout occured when executing command.")
      return None
    except OSError:
      _LOGGER.debug("Failed to connect to endpoint.")
      return None

  async def _exec_get(self, mode, action, key_to_extract):
    return await self._exec_cmd(mode, '<name>{0}</name>'.format(action), key_to_extract)

  async def _exec_set(self, mode, action, property_name, value):
    if type(value) is str:
      value_type = 'str'
    else:
      value_type = 'dec'
    cmd = '<name>{0}</name><p type="{3}" name="{1}" val="{2}"/>'.format(action, property_name, value, value_type)
    return await self._exec_cmd(mode, cmd, property_name)

  async def get_state(self):
    return await self._exec_get('UIC','GetPowerStatus', 'powerStatus')

  async def set_state(self, key):
    await self._exec_set('UIC','SetPowerStatus', 'powerStatus', int(key))

  async def get_main_info(self):
    return await self._exec_get('UIC','GetMainInfo')

  async def get_volume(self):
    return await self._exec_get('UIC','GetVolume', 'volume')

  async def set_volume(self, volume):
    await self._exec_set('UIC','SetVolume', 'volume', int(volume))

  async def get_speaker_name(self):
    return await self._exec_get('UIC','GetSpkName', 'spkname')

  async def get_radio_info(self):
    return await self._exec_get('CPM','GetRadioInfo', 'title')

  async def get_radio_image(self):
    return await self._exec_get('CPM','GetRadioInfo', 'thumbnail')

  async def get_muted(self):
    return await self._exec_get('UIC','GetMute', 'mute') == BOOL_ON

  async def set_muted(self, mute):
    if mute:
      await self._exec_set('UIC','SetMute', 'mute', BOOL_ON)  
    else:
      await self._exec_set('UIC','SetMute', 'mute', BOOL_OFF)  

  async def get_source(self):
    return await self._exec_get('UIC','GetFunc', 'function')

  async def get_mode(self):
    return await self._exec_get('UIC','GetFunc', 'submode')

  async def set_source(self, source):
    await self._exec_set('UIC','SetFunc', 'function', source)

class MultiRoomDevice(MediaPlayerDevice):
  """Representation of a Samsung MultiRoom device."""
  def __init__(self, name, max_volume, api):
    _LOGGER.info('Initializing MultiRoomDevice')
    self._name = name
    self.api = api
    self._state = STATE_OFF
    self._current_source = None
    self._media_title = ''
    self._image_url = ''
    self._volume = 0
    self._mode = ''
    self._muted = False
    self._max_volume = max_volume

  @property
  def supported_features(self):
    """Flag media player features that are supported."""
    return SUPPORT_SAMSUNG_MULTI_ROOM

  @property
  def name(self):
    """Return the name of the device."""
    return self._name

  @property
  def media_title(self):
    """Title of current playing media."""
    return self._media_title

  @property
  def media_image_url(self):
    """Url for image of current playing media."""
    return self._image_url

  @property
  def state(self):
    """Return the state of the device."""
    return self._state

  @property
  def mode(self):
    """Return the sub mode of the device."""
    return self._mode

  @property
  def volume_level(self):
    """Return the volume level."""
    return self._volume

  async def async_set_volume_level(self, volume):
    """Sets the volume level."""
    await self.api.set_volume(volume * self._max_volume)
    await self.async_update()

  @property
  def is_volume_muted(self):
    """Boolean if volume is currently muted."""
    return self._muted

  async def async_mute_volume(self, mute):
    """Sets volume mute to true."""
    self._muted = mute
    await self.api.set_muted(self._muted)
    await self.async_update()

  @property
  def source(self):
    """Return the current source."""
    return self._current_source

  @property
  def source_list(self):
    """List of available input sources."""
    return sorted(MULTI_ROOM_SOURCE_TYPE)

  async def async_select_source(self, source):
    """Select input source."""
    if source not in MULTI_ROOM_SOURCE_TYPE:
      _LOGGER.error("Unsupported source")
      return

    await self.api.set_source(source)
    await self.async_update()

  async def turn_off(self):
      """Turn the media player off."""
      await self.api.set_state(0)

  async def turn_on(self):
      """Turn the media player on."""
      await self.api.set_state(1)

  @util.Throttle(MIN_TIME_BETWEEN_SCANS, MIN_TIME_BETWEEN_FORCED_SCANS)
  async def async_update(self):
    """Update the media player State."""
    _LOGGER.info('Refreshing state...')
    "Get Power State"
    state = await self.api.get_state()
    if state and int(state) == 1:
      "If Power is ON, update other values"
      self._state = STATE_PLAYING
      "Get Current Source"
      source = await self.api.get_source()
      if source:
        self._current_source = source
      "Get Volume"
      volume = await self.api.get_volume()
      if volume:
        self._volume = int(volume) / self._max_volume
      "Get Mute State"
      muted = await self.api.get_muted()
      if muted:
        self._muted = muted
      "Getting current mode"
      mode = await self.api.get_mode()
      if mode and str(mode) == 'cp':
        title = await self.api.get_radio_info()
        self._media_title = str(title)
        self._image_url = await self.api.get_radio_image()
      else:
        self._media_title = None
    else:
      self._state = STATE_OFF


def setup_platform(hass, config, add_devices, discovery_info=None):
  """Set up the Samsung MultiRoom platform."""
  ip = config.get(CONF_HOST)
  port = config.get(CONF_PORT)
  name = config.get(CONF_NAME)
  max_volume = int(config.get(CONF_MAX_VOLUME))
  session = async_get_clientsession(hass)
  api = MultiRoomApi(ip, port, session, hass)
  add_devices([MultiRoomDevice(name, max_volume, api)], True)
