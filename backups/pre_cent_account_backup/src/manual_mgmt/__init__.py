"""
Manual Position Management & Adoption Subsystem.
Tags: [SAFETY], [VIDEO/KNOWLEDGE], [ASSUMPTION]
"""

from src.manual_mgmt.contracts import (
    PositionClass,
    ManagementMode,
    ManualMgmtConfig,
    ManualPositionRecord,
    AdoptionAssessment
)
from src.manual_mgmt.classifier import classify_position, clean_base_symbol
from src.manual_mgmt.registry import ManualPositionRegistry
from src.manual_mgmt.assessor import ManualPositionAssessor
from src.manual_mgmt.policy import ManualMgmtPolicy
from src.manual_mgmt.executor import ManualMgmtExecutor
from src.manual_mgmt.detector import ManualPositionDetector

__all__ = [
    "PositionClass",
    "ManagementMode",
    "ManualMgmtConfig",
    "ManualPositionRecord",
    "AdoptionAssessment",
    "classify_position",
    "clean_base_symbol",
    "ManualPositionRegistry",
    "ManualPositionAssessor",
    "ManualMgmtPolicy",
    "ManualMgmtExecutor",
    "ManualPositionDetector"
]
