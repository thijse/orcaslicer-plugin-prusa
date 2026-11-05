"""Handlers of the Prusa tab, one class per side tab."""

from .history import HistoryTab
from .settings import SettingsTab
from .status import StatusTab
from .storage import StorageTab
from .tools import ToolsTab

TABS = (StatusTab, StorageTab, ToolsTab, HistoryTab, SettingsTab)
