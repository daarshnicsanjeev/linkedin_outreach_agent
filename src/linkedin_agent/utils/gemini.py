"""
Gemini AI Integration
=====================
Shared Gemini API client for text classification, generation, and vision.
"""

import os
import asyncio
import base64
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class GeminiClient:
    """
    Wrapper around Google Gemini API for LinkedIn agent tasks.
    
    Features:
    - Text classification (legal professional detection, role classification)
    - Comment/response generation
    - Vision-based verification
    - Rate limiting and error handling
    """
    
    def __init__(self, api_key: str = None, model: str = "gemini-2.0-flash"):
        if not GENAI_AVAILABLE:
            raise ImportError("google-genai package not installed")
        
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        
        self.model = model
        self.client = genai.Client(api_key=self.api_key)
    
    async def generate_text(self, prompt: str, 
                            system_instruction: str = None,
                            temperature: float = 0.7,
                            max_tokens: int = 1024) -> str:
        """
        Generate text using Gemini.
        
        Args:
            prompt: The user prompt
            system_instruction: Optional system instruction
            temperature: Creativity level (0.0-1.0)
            max_tokens: Maximum response length
            
        Returns:
            Generated text content
        """
        try:
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            
            if system_instruction:
                config.system_instruction = system_instruction
            
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=prompt,
                config=config
            )
            
            return response.text.strip() if response.text else ""
            
        except Exception as e:
            raise RuntimeError(f"Gemini generation error: {e}")
    
    def generate_text_sync(self, prompt: str,
                           system_instruction: str = None,
                           temperature: float = 0.7) -> str:
        """Synchronous version of generate_text."""
        try:
            config = types.GenerateContentConfig(
                temperature=temperature,
            )
            
            if system_instruction:
                config.system_instruction = system_instruction
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config
            )
            
            return response.text.strip() if response.text else ""
            
        except Exception as e:
            raise RuntimeError(f"Gemini generation error: {e}")
    
    def generate(self, prompt: str, temperature: float = 0.7) -> str:
        """
        Simple text generation (alias for generate_text_sync).
        
        This is the primary method used by agents for text generation.
        
        Args:
            prompt: The text prompt to send to Gemini
            temperature: Creativity level (0.0-1.0), default 0.7
            
        Returns:
            Generated text response
        """
        return self.generate_text_sync(prompt, temperature=temperature)
    
    async def classify_text(self, text: str, categories: List[str],
                           context: str = None) -> Dict[str, Any]:
        """
        Classify text into one of the provided categories.
        
        Args:
            text: Text to classify
            categories: List of possible categories
            context: Optional context for classification
            
        Returns:
            Dict with 'category', 'confidence', and 'reasoning'
        """
        category_list = ", ".join(categories)
        
        prompt = f"""Classify the following text into one of these categories: {category_list}

Text to classify:
{text}

{f'Context: {context}' if context else ''}

Respond in this exact format:
CATEGORY: [chosen category]
CONFIDENCE: [0.0-1.0]
REASONING: [brief explanation]"""

        response = await self.generate_text(prompt, temperature=0.3)
        
        # Parse response
        result = {"category": categories[0], "confidence": 0.5, "reasoning": ""}
        
        for line in response.split('\n'):
            line = line.strip()
            if line.startswith("CATEGORY:"):
                result["category"] = line.split(":", 1)[1].strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    result["confidence"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("REASONING:"):
                result["reasoning"] = line.split(":", 1)[1].strip()
        
        return result
    
    async def is_legal_professional(self, headline: str) -> bool:
        """
        Check if a LinkedIn headline indicates a legal professional.
        
        Args:
            headline: LinkedIn profile headline
            
        Returns:
            True if person appears to be a practicing legal professional
        """
        prompt = f"""Is this person a practicing legal professional (lawyer, attorney, partner at a law firm)?

Headline: {headline}

Answer YES or NO only. Exclude legal tech, legal ops, students, paralegals, and recruiters."""

        response = await self.generate_text(prompt, temperature=0.1)
        return response.strip().upper().startswith("YES")
    
    def is_legal_professional_sync(self, headline: str) -> bool:
        """Synchronous version of is_legal_professional."""
        prompt = f"""Is this person a practicing legal professional (lawyer, attorney, partner at a law firm)?

Headline: {headline}

Answer YES or NO only. Exclude legal tech, legal ops, students, paralegals, and recruiters."""

        response = self.generate_text_sync(prompt, temperature=0.1)
        return response.strip().upper().startswith("YES")
    
    async def analyze_screenshot(self, screenshot_bytes: bytes, 
                                  prompt: str) -> str:
        """
        Analyze a screenshot using Gemini Vision.
        
        Args:
            screenshot_bytes: PNG screenshot as bytes
            prompt: Question or instruction about the image
            
        Returns:
            Analysis text
        """
        try:
            image_data = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            contents = [
                types.Part.from_text(prompt),
                types.Part.from_bytes(
                    data=screenshot_bytes,
                    mime_type="image/png"
                )
            ]
            
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=contents
            )
            
            return response.text.strip() if response.text else ""
            
        except Exception as e:
            raise RuntimeError(f"Vision analysis error: {e}")
    
    async def verify_action(self, screenshot_bytes: bytes,
                            expected_state: str) -> Dict[str, Any]:
        """
        Verify if an expected UI state is present in the screenshot.
        
        Args:
            screenshot_bytes: PNG screenshot
            expected_state: Description of expected state
            
        Returns:
            Dict with 'verified' (bool), 'confidence' (float), 'details' (str)
        """
        prompt = f"""Look at this screenshot and determine if: {expected_state}

Respond in this exact format:
VERIFIED: [YES/NO]
CONFIDENCE: [0.0-1.0]
DETAILS: [what you see]"""

        response = await self.analyze_screenshot(screenshot_bytes, prompt)
        
        result = {"verified": False, "confidence": 0.5, "details": ""}
        
        for line in response.split('\n'):
            line = line.strip()
            if line.startswith("VERIFIED:"):
                result["verified"] = "YES" in line.upper()
            elif line.startswith("CONFIDENCE:"):
                try:
                    result["confidence"] = float(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif line.startswith("DETAILS:"):
                result["details"] = line.split(":", 1)[1].strip()
        
        return result


# Module-level client singleton
_client = None

def get_gemini_client(api_key: str = None) -> GeminiClient:
    """Get or create the global GeminiClient instance."""
    global _client
    if _client is None:
        _client = GeminiClient(api_key=api_key)
    return _client
