"""Handlers of the Prusa tab, one class per side tab."""

from .catalog import CatalogTab
from .history import HistoryTab
from .settings import SettingsTab
from .status import StatusTab
from .storage import StorageTab
from .tools import ToolsTab
from .wizard import SetupWizard

TABS = (StatusTab, StorageTab, ToolsTab, CatalogTab, HistoryTab, SettingsTab, SetupWizard)
