"""Многоступенчатый Context Compiler."""

from .budget import BudgetSnapshot, ContextBudgetError, ContextBudgetManager
from .classifier import Classification, MessageClassifier, classify_message
from .compiler import ContextCompiler, ContextIntegrityError
from .diagnostic import Diagnostic, DiagnosticLifecycle, normalize_diagnostics
from .packer import ContextPacker, PackingError
from .policy import CompressionDecision, decide_compression
from .tokenizer import ApproximateTokenCounter, TokenCounter

__all__ = [
    "ApproximateTokenCounter",
    "BudgetSnapshot",
    "Classification",
    "CompressionDecision",
    "ContextBudgetError",
    "ContextBudgetManager",
    "ContextCompiler",
    "ContextIntegrityError",
    "ContextPacker",
    "Diagnostic",
    "DiagnosticLifecycle",
    "MessageClassifier",
    "PackingError",
    "TokenCounter",
    "classify_message",
    "decide_compression",
    "normalize_diagnostics",
]
