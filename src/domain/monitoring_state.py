from enum import Enum


class MonitoringState(str, Enum):
    NORMAL = 'NORMAL'
    SURVEILLANCE = 'SURVEILLANCE'
    ALERT = 'ALERT'
    CRITICAL = 'CRITICAL'
    DISCONNECTED = 'DISCONNECTED'
