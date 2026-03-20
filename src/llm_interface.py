"""
VERIFY Framework: LLM Interface Module
Provides a unified interface for interacting with LLMs (OpenAI GPT-4o, DeepSeek, or local models).
Handles prompt construction, API calls, response parsing, and logging.
"""

import os
import json
import time
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any, Set
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Structured LLM response."""
    raw_text: str
    assertions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    timestamp: str = ""


class LLMInterface:
    """Unified interface for LLM API calls with logging."""
    
    def __init__(self, 
                 provider: str = "openai",
                 model: str = "gpt-4o",
                 api_key: Optional[str] = None,
                 log_dir: str = "output/logs",
                 temperature: float = 0.3,
                 max_tokens: int = 4096):
        """
        Initialize LLM interface.
        
        Args:
            provider: 'openai', 'deepseek', or 'local'
            model: Model name
            api_key: API key (or set via environment variable)
            log_dir: Directory for prompt/response logs
            temperature: Sampling temperature
            max_tokens: Maximum response tokens
        """
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.call_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        
        # Set up API key
        if api_key:
            self.api_key = api_key
        elif provider == "openai":
            self.api_key = os.environ.get("OPENAI_API_KEY", "")
        elif provider == "deepseek":
            self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        elif provider == "gemini":
            self.api_key = os.environ.get("GEMINI_API_KEY", "")
        else:
            self.api_key = ""
        
        # Initialize client
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize the API client."""
        try:
            if self.provider == "openai":
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            elif self.provider == "deepseek":
                from openai import OpenAI
                self.client = OpenAI(
                    api_key=self.api_key,
                    base_url="https://api.deepseek.com"
                )
            elif self.provider == "gemini":
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            else:
                print(f"[WARNING] Unknown provider '{self.provider}', using mock mode")
                self.client = None
        except ImportError:
            print("[WARNING] openai package not installed. Using mock mode.")
            print("  Install with: pip install openai")
            self.client = None
        except Exception as e:
            print(f"[WARNING] Failed to initialize client: {e}. Using mock mode.")
            self.client = None
    
    def call(self, prompt: str, system_prompt: str = "", tag: str = "general") -> LLMResponse:
        """
        Make an LLM API call.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            tag: Tag for logging purposes
            
        Returns:
            LLMResponse with raw text and parsed assertions
        """
        self.call_count += 1
        timestamp = datetime.now().isoformat()
        
        # Log the prompt
        self._log_prompt(prompt, system_prompt, tag, timestamp)
        
        if self.client is None:
            return self._mock_response(prompt, tag, timestamp)
        
        try:
            if self.provider == "gemini":
                from google.genai import types
                
                config = types.GenerateContentConfig(
                    system_instruction=system_prompt if system_prompt else None,
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                )
                
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config
                )
                raw_text = response.text
                prompt_tokens = response.usage_metadata.prompt_token_count if hasattr(response, "usage_metadata") and response.usage_metadata else 0
                completion_tokens = response.usage_metadata.candidates_token_count if hasattr(response, "usage_metadata") and response.usage_metadata else 0
            else:
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )
                
                raw_text = response.choices[0].message.content
                prompt_tokens = response.usage.prompt_tokens if response.usage else 0
                completion_tokens = response.usage.completion_tokens if response.usage else 0
            
            self.total_input_tokens += prompt_tokens
            self.total_output_tokens += completion_tokens
            
            result = LLMResponse(
                raw_text=raw_text,
                assertions=self._extract_assertions(raw_text),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                model=self.model,
                timestamp=timestamp
            )
            
            # Log the response
            self._log_response(result, tag, timestamp)
            
            return result
            
        except Exception as e:
            print(f"[ERROR] LLM API call failed: {e}")
            return self._mock_response(prompt, tag, timestamp, error=str(e))
    
    def _extract_assertions(self, text: str) -> List[str]:
        """Extract individual SVA assertions from LLM response text."""
        assertions = []
        
        # Extract code blocks
        code_blocks = re.findall(r'```(?:systemverilog|sv|verilog)?\s*\n(.*?)```', text, re.DOTALL)
        
        if code_blocks:
            full_code = "\n".join(code_blocks)
        else:
            full_code = text
        
        # Split into individual assertions (property...assert pairs)
        # Pattern: optional comment + property declaration + endproperty + assert
        assertion_pattern = re.compile(
            r'((?://[^\n]*\n)*'           # Optional comments
            r'property\s+\w+.*?'           # property declaration
            r'endproperty\s*\n?'           # endproperty
            r'assert\s+property[^;]*;'     # assert statement
            r'(?:\s*else\s+\$\w+\([^)]*\);)?)',  # optional else clause
            re.DOTALL
        )
        
        for match in assertion_pattern.finditer(full_code):
            assertion_text = match.group(0).strip()
            if assertion_text:
                assertions.append(assertion_text)
        
        # If no structured assertions found, try to extract any property blocks
        if not assertions:
            prop_pattern = re.compile(
                r'((?://[^\n]*\n)*property\s+.*?endproperty)',
                re.DOTALL
            )
            for match in prop_pattern.finditer(full_code):
                assertions.append(match.group(0).strip())
        
        return assertions
    
    def _mock_response(self, prompt: str, tag: str, timestamp: str, error: str = "") -> LLMResponse:
        """Generate a mock response when API is not available."""
        mock_text = f"""// Mock SVA response (API not configured)
// Tag: {tag}
// To use real LLM, set OPENAI_API_KEY or DEEPSEEK_API_KEY environment variable

// [SAFETY] Mock assertion - FIFO should not overflow
property p_mock_no_overflow;
    @(posedge clk) disable iff (!rst_n)
    full |-> !wr_en;
endproperty
assert property (p_mock_no_overflow) else $error("Overflow detected");

// [RESET] Mock assertion - Reset clears state
property p_mock_reset;
    @(posedge clk)
    !rst_n |-> ##1 (count == 0);
endproperty
assert property (p_mock_reset) else $error("Reset failed");
"""
        if error:
            mock_text = f"// API Error: {error}\n" + mock_text
        
        result = LLMResponse(
            raw_text=mock_text,
            assertions=self._extract_assertions(mock_text),
            model="mock",
            timestamp=timestamp
        )
        
        self._log_response(result, tag, timestamp)
        return result
    
    def _log_prompt(self, prompt: str, system_prompt: str, tag: str, timestamp: str):
        """Log the prompt to a file."""
        log_file = self.log_dir / f"prompt_{self.call_count:04d}_{tag}.txt"
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"=== PROMPT LOG ===\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Call #: {self.call_count}\n")
            f.write(f"Tag: {tag}\n")
            f.write(f"Model: {self.model}\n")
            f.write(f"Temperature: {self.temperature}\n\n")
            if system_prompt:
                f.write(f"--- SYSTEM PROMPT ---\n{system_prompt}\n\n")
            f.write(f"--- USER PROMPT ---\n{prompt}\n")
    
    def _log_response(self, response: LLMResponse, tag: str, timestamp: str):
        """Log the response to a file."""
        log_file = self.log_dir / f"response_{self.call_count:04d}_{tag}.txt"
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"=== RESPONSE LOG ===\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Call #: {self.call_count}\n")
            f.write(f"Tag: {tag}\n")
            f.write(f"Model: {response.model}\n")
            f.write(f"Input tokens: {response.prompt_tokens}\n")
            f.write(f"Output tokens: {response.completion_tokens}\n")
            f.write(f"Assertions extracted: {len(response.assertions)}\n\n")
            f.write(f"--- RAW RESPONSE ---\n{response.raw_text}\n\n")
            f.write(f"--- EXTRACTED ASSERTIONS ---\n")
            for i, a in enumerate(response.assertions):
                f.write(f"\n[Assertion {i+1}]\n{a}\n")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        return {
            "total_calls": self.call_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "model": self.model,
            "provider": self.provider
        }


class AssertionExtractor:
    """Utility class for parsing and normalizing SVA assertions."""
    
    @staticmethod
    def parse_assertion(text: str) -> Dict[str, str]:
        """Parse a single assertion into its components."""
        result = {
            "comment": "",
            "classification": "",
            "property_name": "",
            "property_body": "",
            "assert_statement": "",
            "full_text": text
        }
        
        # Extract comment and classification
        comment_match = re.search(r'//\s*\[(\w+)\]\s*(.*)', text)
        if comment_match:
            result["classification"] = comment_match.group(1)
            result["comment"] = comment_match.group(2).strip()
        
        # Extract property name
        prop_match = re.search(r'property\s+(\w+)', text)
        if prop_match:
            result["property_name"] = prop_match.group(1)
        
        # Extract property body (between property name; and endproperty)
        body_match = re.search(r'property\s+\w+\s*;?\s*(.*?)endproperty', text, re.DOTALL)
        if body_match:
            result["property_body"] = body_match.group(1).strip()
        
        return result
    
    @staticmethod
    def normalize_assertion(text: str) -> str:
        """Normalize whitespace and formatting of an assertion."""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Ensure consistent property/endproperty formatting
        text = re.sub(r'endproperty', '\nendproperty', text)
        text = re.sub(r'assert property', '\nassert property', text)
        return text.strip()
    
    @staticmethod
    def extract_signal_names_from_assertion(text: str) -> Set[str]:
        """Extract all potential signal names referenced in an assertion."""
        # Remove keywords and operators
        keywords = {
            'property', 'endproperty', 'assert', 'posedge', 'negedge', 
            'disable', 'iff', 'clk', 'rst_n', 'clk_i', 'rst_ni',
            'begin', 'end', 'if', 'else', 'past', 'rose', 'fell', 'stable',
            'error', 'warning', 'info', 'fatal', 'logic', 'bit', 'int',
            'true', 'false'
        }
        
        identifiers = set(re.findall(r'\b([a-zA-Z_]\w*)\b', text))
        return identifiers - keywords
