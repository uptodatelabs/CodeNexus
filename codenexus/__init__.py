"""CodeNexus: The context engine for AI coding agents."""

from ._version import __version__
from .graph import DependencyGraph, Edge, Node
from .llm import LLAMA_CPP_AVAILABLE, LLMConfig, LocalLLM, get_llm, init_llm
from .memory import Decision, DecisionType, Session, SessionMemory, get_memory
from .parser import CodeParser
from .server import CodeNexusServer
from .workspace import MultiRepoWorkspace, RepoConfig, WorkspaceConfig

__author__ = "CodeNexus Contributors"

__all__ = [
    "__version__",
    "DependencyGraph",
    "Node",
    "Edge",
    "CodeParser",
    "CodeNexusServer",
    "LocalLLM",
    "LLMConfig",
    "get_llm",
    "init_llm",
    "LLAMA_CPP_AVAILABLE",
    "MultiRepoWorkspace",
    "WorkspaceConfig",
    "RepoConfig",
    "SessionMemory",
    "Session",
    "Decision",
    "DecisionType",
    "get_memory",
]
