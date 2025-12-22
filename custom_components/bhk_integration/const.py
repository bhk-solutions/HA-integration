DOMAIN = "bhk_integration"

CONF_GATEWAY_MAC = "mac"
CONF_GATEWAY_IP = "ip"
CONF_GATEWAY_TYPE = "type"
CONF_GATEWAY_HW_VERSION = "hardware_version"
CONF_RETRY_INTERVAL = "retry_interval"
CONF_LOCAL_BIND_IP = "local_bind_ip"

DISCOVERY_MESSAGE = "DISCOVER_GATEWAY"
DISCOVERY_BROADCAST_PORT = 50000
GATEWAY_RESPONSE_PORT = 50002
DEFAULT_RETRY_INTERVAL = 10
GATEWAY_COMMAND_PORT = 50000
DISCOVERY_WINDOW = 30
DEFAULT_JOIN_WINDOW_SECONDS = 120

SIGNAL_LIGHT_REGISTER = "bhk_integration_light_register"
SIGNAL_LIGHT_STATE = "bhk_integration_light_state"
SIGNAL_COVER_REGISTER = "bhk_integration_cover_register"
SIGNAL_COVER_STATE = "bhk_integration_cover_state"
SIGNAL_DEVICE_JOIN = "bhk_integration_device_join"
SIGNAL_DEVICE_REPORT = "bhk_integration_device_report"
SIGNAL_ZB_REPORT = "bhk_integration_zb_report"
SIGNAL_GATEWAY_ALIVE = "bhk_integration_gateway_alive"
SIGNAL_JOIN_WINDOW = "bhk_integration_join_window"

# Gateway availability timeout (seconds) – if no alive within this window, mark unavailable
GATEWAY_ALIVE_TIMEOUT = 70
