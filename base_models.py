"""Base models and abstract classes for ShootyBot data management."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, TypeVar, Generic, Set, Union
import logging

from utils import get_utc_timestamp, log_error


T = TypeVar('T')


class BaseModel(ABC):
    """Abstract base class for all data models."""
    
    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary representation."""
        pass
    
    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BaseModel':
        """Create model instance from dictionary."""
        pass
    
    def __repr__(self) -> str:
        """String representation of the model."""
        return f"{self.__class__.__name__}({self.to_dict()})"


class BaseManager(ABC, Generic[T]):
    """Abstract base class for data managers."""
    
    def __init__(self):
        self._cache: Dict[Any, T] = {}
        self._modified: Set[Any] = set()
    
    @abstractmethod
    def get(self, key: Any) -> Optional[T]:
        """Get an item by key."""
        pass
    
    @abstractmethod
    def create(self, key: Any, **kwargs) -> T:
        """Create a new item."""
        pass
    
    @abstractmethod
    def save(self, key: Any) -> bool:
        """Save an item to persistent storage."""
        pass
    
    @abstractmethod
    def delete(self, key: Any) -> bool:
        """Delete an item."""
        pass
    
    def exists(self, key: Any) -> bool:
        """Check if an item exists."""
        return key in self._cache or self._exists_in_storage(key)
    
    @abstractmethod
    def _exists_in_storage(self, key: Any) -> bool:
        """Check if item exists in persistent storage."""
        pass
    
    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()
        self._modified.clear()
    
    def mark_modified(self, key: Any) -> None:
        """Mark an item as modified."""
        self._modified.add(key)
    
    def save_all_modified(self) -> int:
        """Save all modified items."""
        saved = 0
        for key in list(self._modified):
            if self.save(key):
                saved += 1
                self._modified.discard(key)
        return saved


class TimestampedModel(BaseModel):
    """Base model with automatic timestamp tracking."""
    
    def __init__(self):
        self.created_at: str = get_utc_timestamp()
        self.updated_at: str = get_utc_timestamp()
    
    def update_timestamp(self) -> None:
        """Update the last modified timestamp."""
        self.updated_at = get_utc_timestamp()
    
    def to_dict(self) -> Dict[str, Any]:
        """Include timestamps in dictionary representation."""
        return {
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class StatefulModel(TimestampedModel):
    """Base model with state tracking."""
    
    VALID_STATES: List[str] = []  # Override in subclasses
    
    def __init__(self, initial_state: Optional[str] = None):
        super().__init__()
        self._state: str = initial_state or self.get_default_state()
        self._state_history: List[Dict[str, Any]] = []
    
    @property
    def state(self) -> str:
        """Get current state."""
        return self._state
    
    @state.setter
    def state(self, new_state: str) -> None:
        """Set state with validation and history tracking."""
        if new_state not in self.VALID_STATES:
            raise ValueError(f"Invalid state: {new_state}. Valid states: {self.VALID_STATES}")
        
        if new_state != self._state:
            self._state_history.append({
                'from_state': self._state,
                'to_state': new_state,
                'timestamp': get_utc_timestamp()
            })
            self._state = new_state
            self.update_timestamp()
    
    @classmethod
    def get_default_state(cls) -> str:
        """Get the default initial state."""
        return cls.VALID_STATES[0] if cls.VALID_STATES else 'unknown'
    
    def get_state_history(self) -> List[Dict[str, Any]]:
        """Get state transition history."""
        return self._state_history.copy()
    
    def to_dict(self) -> Dict[str, Any]:
        """Include state information in dictionary."""
        data = super().to_dict()
        data.update({
            'state': self._state,
            'state_history': self._state_history
        })
        return data


class ValidatedModel(BaseModel):
    """Base model with validation support."""
    
    def __init__(self):
        self._validation_errors: List[str] = []
    
    @abstractmethod
    def validate(self) -> bool:
        """Validate the model data."""
        pass
    
    def add_validation_error(self, error: str) -> None:
        """Add a validation error."""
        self._validation_errors.append(error)
    
    def clear_validation_errors(self) -> None:
        """Clear all validation errors."""
        self._validation_errors.clear()
    
    def get_validation_errors(self) -> List[str]:
        """Get all validation errors."""
        return self._validation_errors.copy()
    
    def is_valid(self) -> bool:
        """Check if model is valid."""
        self.clear_validation_errors()
        return self.validate()




class DatabaseBackedManager(BaseManager[T]):
    """Manager backed by database storage."""
    
    def __init__(self, table_name: str):
        super().__init__()
        self.table_name = table_name
        from database import database_manager
        self.db = database_manager
    
    def _exists_in_storage(self, key: Any) -> bool:
        """Check if item exists in database."""
        # This would be implemented based on specific database schema
        return False
    
    def commit_transaction(self) -> bool:
        """Commit any pending database transaction."""
        try:
            # Database manager handles transactions internally
            return True
        except Exception as e:
            log_error("committing transaction", e)
            return False
    
    def rollback_transaction(self) -> bool:
        """Rollback any pending database transaction."""
        try:
            # Database manager handles transactions internally
            return True
        except Exception as e:
            log_error("rolling back transaction", e)
            return False
