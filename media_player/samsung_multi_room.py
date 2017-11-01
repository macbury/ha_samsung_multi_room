import urllib.parse
import requests
import logging
import voluptuous as vol

_LOGGER      = logging.getLogger(__name__)
REQUIREMENTS = ['xmltodict==0.11.0']
DEPENDENCIES = ['http']

from homeassistant.helpers import config_validation as cv

from homeassistant.components.media_player import (
  PLATFORM_SCHEMA,
  MEDIA_TYPE_CHANNEL,
  SUPPORT_TURN_ON,
  SUPPORT_TURN_OFF,
  SUPPORT_VOLUME_MUTE,
  SUPPORT_SELECT_SOURCE,
  SUPPORT_VOLUME_SET,
  MediaPlayerDevice
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
  'bt'
]

BOOL_OFF = 'off'
BOOL_ON = 'on'

SUPPORT_SAMSUNG_MULTI_ROOM = SUPPORT_VOLUME_SET | SUPPORT_VOLUME_MUTE | SUPPORT_SELECT_SOURCE

CONF_MAX_VOLUME = 'max_volume'
CONF_PORT = 'port'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
  vol.Required(CONF_HOST, default='127.0.0.1'): cv.string,
  vol.Optional(CONF_PORT, default='55001'): cv.string,
  vol.Optional(CONF_MAX_VOLUME, default='100'): cv.string
})


class MultiRoomApi():
  def __init__(self, ip, port):
    self.ip = ip
    self.port = port
    self.endpoint = 'http://{0}:{1}'.format(ip, port)

  def _exec_cmd(self, cmd, key_to_extract):
    import xmltodict
    query = urllib.parse.urlencode({ "cmd": cmd }, quote_via=urllib.parse.quote)
    url = '{0}/UIC?{1}'.format(self.endpoint, query)

    req = requests.get(url, timeout=10)
    response = xmltodict.parse(req.text)
    return response['UIC']['response'][key_to_extract]

  def _exec_get(self, action, key_to_extract):
    return self._exec_cmd('<name>{0}</name>'.format(action), key_to_extract)

  def _exec_set(self, action, property_name, value):
    if type(value) is str:
      value_type = 'str'
    else:
      value_type = 'dec'
    cmd = '<name>{0}</name><p type="{3}" name="{1}" val="{2}"/>'.format(action, property_name, value, value_type)
    return self._exec_cmd(cmd, property_name)

  def get_main_info(self):
    return self._exec_get('GetMainInfo')

  def get_volume(self):
    return int(self._exec_get('GetVolume', 'volume'))

  def set_volume(self, volume):
    return self._exec_set('SetVolume', 'volume', int(volume))

  def get_speaker_name(self):
    return self._exec_get('GetSpkName', 'spkname')

  def get_muted(self):
    return self._exec_get('GetMute', 'mute') == BOOL_ON

  def set_muted(self, mute):
    if mute:
      return self._exec_set('SetMute', 'mute', BOOL_ON)  
    else:
      return self._exec_set('SetMute', 'mute', BOOL_OFF)  

  def get_source(self):
    return self._exec_get('GetFunc', 'function')

  def set_source(self, source):
    return self._exec_set('SetFunc', 'function', source)

class MultiRoomDevice(MediaPlayerDevice):
  def __init__(self, name, max_volume, api):
    self._name = name
    self.api = api
    self._state = STATE_OFF
    self._current_source = None
    self._volume = 0
    self._muted = False
    self._max_volume = max_volume
    self.update()

  @property
  def supported_features(self):
    return SUPPORT_SAMSUNG_MULTI_ROOM

  @property
  def name(self):
    return self._name

  @property
  def state(self):
    return self._state

  @property
  def volume_level(self):
    return self._volume

  def set_volume_level(self, volume):
    self.api.set_volume(volume * self._max_volume)

  @property
  def source(self):
    return self._current_source

  @property
  def source_list(self):
    return sorted(MULTI_ROOM_SOURCE_TYPE)

  def select_source(self, source):
    self.api.set_source(source)

  @property
  def is_volume_muted(self):
    return self._muted

  def mute_volume(self, mute):
    self._muted = mute
    self.api.set_muted(self._muted)

  def update(self):
    try:
      _LOGGER.info('Refreshing state...')
      if not self._name:
        self._name = self.api.get_speaker_name()
      self._current_source = self.api.get_source()
      self._volume = self.api.get_volume() / self._max_volume
      self._state = STATE_IDLE
      self._muted = self.api.get_muted()
    except requests.exceptions.ReadTimeout as e:
      self._state = STATE_OFF
      _LOGGER.error('Epic failure:', e)


def setup_platform(hass, config, add_devices, discovery_info=None):
  ip = config.get(CONF_HOST)
  port = config.get(CONF_PORT)
  name = config.get(CONF_NAME)
  max_volume = int(config.get(CONF_MAX_VOLUME))
  api = MultiRoomApi(ip, port)
  add_devices([MultiRoomDevice(name, max_volume, api)], True)
