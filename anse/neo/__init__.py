"""
anse/neo/__init__.py — Neo-AI Terminal Assistant Module for Xavuntu AI & GWAYA v3.
Integrates Vasco0x4/Neo-AI with local open weights (Qwen 14B TPU ReBAR / 3.8 Quant) and GWAYA v3 Zero-Trust Security.
"""

from anse.neo.protocols import MCPProtocol, ProtocolRegistry, ProtocolHandler
from anse.neo.approval import ApprovalHandler, CommandApprovalResult
from anse.neo.core import NeoAI, NeoConfig

__all__ = [
    "NeoAI",
    "NeoConfig",
    "MCPProtocol",
    "ProtocolRegistry",
    "ProtocolHandler",
    "ApprovalHandler",
    "CommandApprovalResult",
]
