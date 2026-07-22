"""CodeNexus: The context engine for AI coding agents."""

__version__ = "0.1.0"
__author__ = "CodeNexus Contributors"

from .graph import DependencyGraph, Node, Edge
from .parser import CodeParser
from .server import CodeNexusServer
from .llm import LocalLLM, LLMConfig, get_llm, init_llm, LLAMA_CPP_AVAILABLE
from .workspace import MultiRepoWorkspace, WorkspaceConfig, RepoConfig
from .memory import SessionMemory, Session, Decision, DecisionType, get_memory

__all__ = [
    "DependencyGraph", "Node", "Edge", 
    "CodeParser", "CodeNexusServer",
    "LocalLLM", "LLMConfig", "get_llm", "init_llm", "LLAMA_CPP_AVAILABLE",
    "MultiRepoWorkspace", "WorkspaceConfig", "RepoConfig",
    "SessionMemory", "Session", "Decision", "DecisionType", "get_memory"
]
