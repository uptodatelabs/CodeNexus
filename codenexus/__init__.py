"""CodeNexus: The context engine for AI coding agents."""

__version__ = "1.0.0"
__author__ = "CodeNexus Contributors"

from .graph import DependencyGraph, Edge, Node
from .license import LicenseManager, LicenseTier, get_license
from .llm import LLAMA_CPP_AVAILABLE, LLMConfig, LocalLLM, get_llm, init_llm
from .memory import Decision, DecisionType, Session, SessionMemory, get_memory
from .parser import CodeParser
from .server import CodeNexusServer
from .workspace import MultiRepoWorkspace, RepoConfig, WorkspaceConfig

__all__ = [
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
    "LicenseManager",
    "LicenseTier",
    "get_license",
]
