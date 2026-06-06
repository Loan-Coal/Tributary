"""
Package: tributary.ai
Layer: ai
Purpose: Grounded AI layer — flow classification, jurisdiction attribution, rule retrieval, citation, and brief narrative. Emits no figures.
Public surface: protocol (AILayerProtocol + I/O models), models, protocols, client, qwen_client, service, fake_client, rag_retriever
"""
from __future__ import annotations

__all__ = [
    "protocol",
    "models",
    "protocols",
    "client",
    "qwen_client",
    "service",
    "fake_client",
    "rag_retriever",
]
