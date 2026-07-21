"""Local LLM integration for CodeNexus using llama-cpp-python."""

import os
import sys
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

# Try to import llama-cpp-python
try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False

@dataclass
class LLMConfig:
    """LLM configuration."""
    model_path: Optional[str] = None
    n_ctx: int = 4096
    n_gpu_layers: int = 0  # Set to -1 for GPU acceleration
    verbose: bool = False
    embedding: bool = False

class LocalLLM:
    """Local LLM for code analysis and context optimization."""
    
    # Recommended models for code analysis
    RECOMMENDED_MODELS = {
        "small": {
            "repo_id": "lmstudio-community/Qwen2.5-Coder-3B-Instruct-GGUF",
            "filename": "*q4_0.gguf",
            "description": "3B parameters, fast, good for simple tasks",
            "size_gb": 2.0
        },
        "medium": {
            "repo_id": "lmstudio-community/Qwen2.5-Coder-7B-Instruct-GGUF",
            "filename": "*q4_0.gguf",
            "description": "7B parameters, balanced performance",
            "size_gb": 4.5
        },
        "large": {
            "repo_id": "lmstudio-community/Qwen2.5-Coder-14B-Instruct-GGUF",
            "filename": "*q4_0.gguf",
            "description": "14B parameters, best quality",
            "size_gb": 9.0
        }
    }
    
    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self.llm: Optional[Llama] = None
        self._loaded = False
    
    def is_available(self) -> bool:
        """Check if llama-cpp-python is installed."""
        return LLAMA_CPP_AVAILABLE
    
    def load_model(self, model_path: Optional[str] = None) -> bool:
        """
        Load the LLM model.
        
        Args:
            model_path: Path to GGUF model file
        
        Returns:
            True if model loaded successfully
        """
        if not LLAMA_CPP_AVAILABLE:
            print("llama-cpp-python not installed. Run: pip install llama-cpp-python")
            return False
        
        path = model_path or self.config.model_path
        if not path or not Path(path).exists():
            print(f"Model not found: {path}")
            return False
        
        try:
            self.llm = Llama(
                model_path=path,
                n_ctx=self.config.n_ctx,
                n_gpu_layers=self.config.n_gpu_layers,
                verbose=self.config.verbose,
                embedding=self.config.embedding
            )
            self._loaded = True
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False
    
    def download_model(self, size: str = "small") -> Optional[str]:
        """
        Download a model from Hugging Face Hub.
        
        Args:
            size: Model size (small, medium, large)
        
        Returns:
            Path to downloaded model or None
        """
        if not LLAMA_CPP_AVAILABLE:
            print("llama-cpp-python not installed. Run: pip install llama-cpp-python")
            return None
        
        if size not in self.RECOMMENDED_MODELS:
            print(f"Unknown model size: {size}. Choose from: small, medium, large")
            return None
        
        model_info = self.RECOMMENDED_MODELS[size]
        print(f"Downloading {size} model ({model_info['size_gb']}GB)...")
        print(f"Repository: {model_info['repo_id']}")
        
        try:
            llm = Llama.from_pretrained(
                repo_id=model_info["repo_id"],
                filename=model_info["filename"],
                verbose=self.config.verbose
            )
            
            # Get the model path from the loaded model
            model_path = str(llm.model_path) if hasattr(llm, 'model_path') else None
            print(f"Model downloaded successfully")
            return model_path
        except Exception as e:
            print(f"Error downloading model: {e}")
            return None
    
    def analyze_intent(self, query: str) -> str:
        """
        Analyze the intent of a query using local LLM.
        
        Args:
            query: User query
        
        Returns:
            Detected intent (explore, debug, modify, refactor)
        """
        if not self._loaded or not self.llm:
            # Fallback to rule-based intent detection
            return self._rule_based_intent(query)
        
        prompt = f"""Analyze the following coding task and determine the intent.
Respond with ONE of: explore, debug, modify, refactor

Task: {query}

Intent:"""
        
        try:
            response = self.llm(
                prompt,
                max_tokens=10,
                stop=["\n", "."],
                echo=False
            )
            intent = response["choices"][0]["text"].strip().lower()
            
            if intent in ["explore", "debug", "modify", "refactor"]:
                return intent
            return "explore"
        except Exception:
            return self._rule_based_intent(query)
    
    def _rule_based_intent(self, query: str) -> str:
        """Rule-based intent detection fallback."""
        query_lower = query.lower()
        
        # Debugging indicators
        if any(word in query_lower for word in ["error", "bug", "fix", "crash", "fail", "exception"]):
            return "debug"
        
        # Refactoring indicators
        if any(word in query_lower for word in ["refactor", "clean", "optimize", "improve", "restructure"]):
            return "refactor"
        
        # Modification indicators
        if any(word in query_lower for word in ["add", "change", "update", "modify", "implement", "create"]):
            return "modify"
        
        # Default to explore
        return "explore"
    
    def compress_context(self, context: str, max_tokens: int = 2000) -> str:
        """
        Compress context to fit within token limits.
        
        Args:
            context: Original context
            max_tokens: Maximum tokens for output
        
        Returns:
            Compressed context
        """
        if not self._loaded or not self.llm:
            # Simple truncation fallback
            words = context.split()
            return " ".join(words[:max_tokens // 2])
        
        prompt = f"""Compress the following code context to key information.
Keep: function signatures, class definitions, imports, key comments.
Remove: implementation details, redundant code, comments.

Original context:
{context[:4000]}

Compressed context:"""
        
        try:
            response = self.llm(
                prompt,
                max_tokens=max_tokens,
                stop=["\n\n\n"],
                echo=False
            )
            return response["choices"][0]["text"].strip()
        except Exception:
            # Fallback to simple truncation
            words = context.split()
            return " ".join(words[:max_tokens // 2])
    
    def generate_summary(self, code: str) -> str:
        """
        Generate a summary of code.
        
        Args:
            code: Code to summarize
        
        Returns:
            Code summary
        """
        if not self._loaded or not self.llm:
            return self._simple_summary(code)
        
        prompt = f"""Summarize the following code in 1-2 sentences.
Focus on: purpose, key functions, dependencies.

Code:
{code[:3000]}

Summary:"""
        
        try:
            response = self.llm(
                prompt,
                max_tokens=100,
                stop=["\n\n"],
                echo=False
            )
            return response["choices"][0]["text"].strip()
        except Exception:
            return self._simple_summary(code)
    
    def _simple_summary(self, code: str) -> str:
        """Simple rule-based summary fallback."""
        lines = code.strip().split("\n")
        
        # Count functions and classes
        functions = sum(1 for line in lines if "def " in line or "function " in line)
        classes = sum(1 for line in lines if "class " in line)
        imports = sum(1 for line in lines if "import " in line or "require(" in line)
        
        parts = []
        if functions:
            parts.append(f"{functions} function(s)")
        if classes:
            parts.append(f"{classes} class(es)")
        if imports:
            parts.append(f"{imports} import(s)")
        
        if parts:
            return f"Code contains {', '.join(parts)}"
        return f"Code with {len(lines)} lines"
    
    def get_model_info(self) -> dict:
        """Get information about the loaded model."""
        if not self._loaded or not self.llm:
            return {"status": "not_loaded"}
        
        return {
            "status": "loaded",
            "model_path": str(self.config.model_path),
            "context_size": self.config.n_ctx,
            "gpu_layers": self.config.n_gpu_layers
        }

# Global LLM instance
_global_llm: Optional[LocalLLM] = None

def get_llm() -> LocalLLM:
    """Get or create global LLM instance."""
    global _global_llm
    if _global_llm is None:
        _global_llm = LocalLLM()
    return _global_llm

def init_llm(model_path: Optional[str] = None, 
             n_gpu_layers: int = 0) -> LocalLLM:
    """
    Initialize the global LLM.
    
    Args:
        model_path: Path to GGUF model
        n_gpu_layers: Number of GPU layers (-1 for all)
    
    Returns:
        Initialized LLM instance
    """
    llm = get_llm()
    llm.config.model_path = model_path
    llm.config.n_gpu_layers = n_gpu_layers
    
    if model_path:
        llm.load_model()
    
    return llm
