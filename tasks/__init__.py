from tasks.task_easy import EasyTask
from tasks.task_medium import MediumTask
from tasks.task_hard import HardTask
from tasks.task_bonus import BonusTask
from tasks.task_security import SecurityTask
from tasks.task_database import DatabaseTask
from tasks.task_failover import FailoverTask
from tasks.task_dns import DnsTask
from tasks.task_waf import WafTask
from tasks.task_thundering_herd import ThunderingHerdTask

__all__ = [
    "EasyTask", "MediumTask", "HardTask", "BonusTask",
    "SecurityTask", "DatabaseTask", "FailoverTask",
    "DnsTask", "WafTask", "ThunderingHerdTask",
]
