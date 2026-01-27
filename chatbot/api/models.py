"""Pydantic models for FastAPI request/response schemas."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    
    question: str = Field(..., description="User's question")
    session_id: str = Field(..., description="Session ID for conversation history")
    model: Optional[str] = Field(None, description="Model name (optional, uses default if not provided)")
    k: Optional[int] = Field(None, description="Number of documents to retrieve (optional)")
    synthesis_strategy: Optional[str] = Field(None, description="Context synthesis strategy (optional)")
    max_new_tokens: Optional[int] = Field(None, description="Maximum tokens to generate (optional)")


class SourceInfo(BaseModel):
    """Source document information."""
    
    document: str = Field(..., description="Source document name")
    score: Optional[str] = Field(None, description="Relevance score")
    content_preview: Optional[str] = Field(None, description="Preview of document content")
    
    @classmethod
    def from_dict(cls, src: dict) -> "SourceInfo":
        """Create SourceInfo from dictionary, converting score to string if needed."""
        score = src.get("score")
        if score is not None and not isinstance(score, str):
            score = str(score)
        return cls(
            document=src.get("document", "unknown"),
            score=score,
            content_preview=src.get("content_preview", ""),
        )


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    
    answer: str = Field(..., description="Generated answer")
    sources: List[SourceInfo] = Field(default_factory=list, description="Retrieved source documents")
    intent: str = Field(..., description="Detected intent type")
    session_id: str = Field(..., description="Session ID")
    cottage_images: Optional[List[str]] = Field(None, description="Cottage image URLs if requested")


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""
    
    status: str = Field(..., description="Status message")
    vector_store_loaded: bool = Field(..., description="Whether vector store is loaded")
    model_loaded: bool = Field(..., description="Whether LLM model is loaded")


class ClearSessionRequest(BaseModel):
    """Request model for clearing session."""
    
    session_id: str = Field(..., description="Session ID to clear")


class ClearSessionResponse(BaseModel):
    """Response model for clear session endpoint."""
    
    status: str = Field(..., description="Status message")
    message: str = Field(..., description="Detailed message")


class ImagesResponse(BaseModel):
    """Response model for images endpoint."""
    
    images: List[str] = Field(..., description="List of image URLs")
