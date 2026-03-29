"""Configuration management for OpenRAG."""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from utils.logging_config import get_logger
from openrag_agent_system_prompt import OPENRAG_AGENT_SYSTEM_PROMPT

logger = get_logger(__name__)


@dataclass
class OpenAIConfig:
    """OpenAI provider configuration."""
    api_key: str = ""
    configured: bool = False


@dataclass
class AnthropicConfig:
    """Anthropic provider configuration."""
    api_key: str = ""
    configured: bool = False


@dataclass
class WatsonXConfig:
    """IBM WatsonX provider configuration."""
    api_key: str = ""
    endpoint: str = ""
    project_id: str = ""
    configured: bool = False


@dataclass
class OllamaConfig:
    """Ollama provider configuration."""
    endpoint: str = ""
    configured: bool = False


@dataclass
class ProvidersConfig:
    """All provider configurations."""
    openai: OpenAIConfig
    anthropic: AnthropicConfig
    watsonx: WatsonXConfig
    ollama: OllamaConfig

    def get_provider_config(self, provider: str):
        """Get configuration for a specific provider."""
        provider_lower = provider.lower()
        if provider_lower == "openai":
            return self.openai
        elif provider_lower == "anthropic":
            return self.anthropic
        elif provider_lower == "watsonx":
            return self.watsonx
        elif provider_lower == "ollama":
            return self.ollama
        else:
            raise ValueError(f"Unknown provider: {provider}")


@dataclass
class KnowledgeConfig:
    """Knowledge/ingestion configuration."""

    embedding_model: str = ""
    embedding_provider: str = "openai"  # Which provider to use for embeddings
    chunk_size: int = 1000
    chunk_overlap: int = 200
    table_structure: bool = True
    ocr: bool = False
    picture_descriptions: bool = False
    index_name: str = "documents"  # OpenSearch index name


@dataclass
class AgentConfig:
    """Agent configuration."""

    llm_model: str = ""
    llm_provider: str = "openai"  # Which provider to use for LLM
    system_prompt: str = OPENRAG_AGENT_SYSTEM_PROMPT


@dataclass
class OnboardingState:
    """Onboarding state configuration."""

    current_step: int = 0
    assistant_message: Optional[Dict[str, Any]] = field(default=None)
    selected_nudge: Optional[str] = field(default=None)
    card_steps: Optional[Dict[str, Any]] = field(default=None)
    upload_steps: Optional[Dict[str, Any]] = field(default=None)
    openrag_docs_filter_id: Optional[str] = field(default=None)
    user_doc_filter_id: Optional[str] = field(default=None)
    openrag_docs_ingested_version: Optional[str] = field(default=None)
    openrag_docs_remote_signature: Optional[str] = field(default=None)


@dataclass
class OpenRAGConfig:
    """Complete OpenRAG configuration."""

    providers: ProvidersConfig
    knowledge: KnowledgeConfig
    agent: AgentConfig
    onboarding: OnboardingState
    edited: bool = False  # Track if manually edited

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpenRAGConfig":
        """Create config from dictionary."""
        providers_data = data.get("providers", {})
        return cls(
            providers=ProvidersConfig(
                openai=OpenAIConfig(**providers_data.get("openai", {})),
                anthropic=AnthropicConfig(**providers_data.get("anthropic", {})),
                watsonx=WatsonXConfig(**providers_data.get("watsonx", {})),
                ollama=OllamaConfig(**providers_data.get("ollama", {})),
            ),
            knowledge=KnowledgeConfig(**data.get("knowledge", {})),
            agent=AgentConfig(**data.get("agent", {})),
            onboarding=OnboardingState(**data.get("onboarding", {})),
            edited=data.get("edited", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return asdict(self)

    def get_llm_provider_config(self):
        """Get the provider configuration for the current LLM provider."""
        return self.providers.get_provider_config(self.agent.llm_provider)

    def get_embedding_provider_config(self):
        """Get the provider configuration for the current embedding provider."""
        return self.providers.get_provider_config(self.knowledge.embedding_provider)


class ConfigManager:
    """Manages OpenRAG configuration from multiple sources."""

    def __init__(self, config_file: Optional[str] = None):
        """Initialize configuration manager.

        Args:
            config_file: Path to configuration file. Defaults to 'config.yaml' in project root.
        """
        self.config_file = Path(config_file) if config_file else Path("config/config.yaml")
        self._config: Optional[OpenRAGConfig] = None

    def load_config(self) -> OpenRAGConfig:
        """Load configuration from environment variables and config file.

        Priority order:
        1. Environment variables (highest)
        2. Configuration file
        3. Defaults (lowest)
        """
        if self._config is not None:
            return self._config

        # Start with defaults
        config_data = {
            "providers": {
                "openai": {},
                "anthropic": {},
                "watsonx": {},
                "ollama": {},
            },
            "knowledge": {},
            "agent": {},
            "onboarding": {},
        }

        # Load from config file if it exists
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    file_config = yaml.safe_load(f) or {}

                # Merge file config
                if "providers" in file_config:
                    for provider in ["openai", "anthropic", "watsonx", "ollama"]:
                        if provider in file_config["providers"]:
                            config_data["providers"][provider].update(
                                file_config["providers"][provider]
                            )

                for section in ["knowledge", "agent", "onboarding"]:
                    if section in file_config:
                        config_data[section].update(file_config[section])

                config_data["edited"] = file_config.get("edited", False)

                logger.info(f"Loaded configuration from {self.config_file}")
            except Exception as e:
                logger.warning(f"Failed to load config file {self.config_file}: {e}")

        # Create config object first to check edited flags
        temp_config = OpenRAGConfig.from_dict(config_data)

        # Override with environment variables (highest priority, but respect edited flags)
        self._load_env_overrides(config_data, temp_config)

        # Create config object
        self._config = OpenRAGConfig.from_dict(config_data)

        logger.debug("Configuration loaded", config=self._config.to_dict())
        return self._config

    def _load_env_overrides(
        self, config_data: Dict[str, Any], temp_config: Optional["OpenRAGConfig"] = None
    ) -> None:
        """Load environment variable overrides, respecting edited flag."""

        # Skip all environment overrides if config has been manually edited
        if temp_config and temp_config.edited:
            logger.debug("Skipping all env overrides - config marked as edited")
            return

        # OpenAI provider settings
        if os.getenv("OPENAI_API_KEY"):
            config_data["providers"]["openai"]["api_key"] = os.getenv("OPENAI_API_KEY")

        # Anthropic provider settings
        if os.getenv("ANTHROPIC_API_KEY"):
            config_data["providers"]["anthropic"]["api_key"] = os.getenv("ANTHROPIC_API_KEY")

        # WatsonX provider settings
        if os.getenv("WATSONX_API_KEY"):
            config_data["providers"]["watsonx"]["api_key"] = os.getenv("WATSONX_API_KEY")
        if os.getenv("WATSONX_ENDPOINT"):
            config_data["providers"]["watsonx"]["endpoint"] = os.getenv("WATSONX_ENDPOINT")
        if os.getenv("WATSONX_PROJECT_ID"):
            config_data["providers"]["watsonx"]["project_id"] = os.getenv("WATSONX_PROJECT_ID")

        # Ollama provider settings
        if os.getenv("OLLAMA_ENDPOINT"):
            config_data["providers"]["ollama"]["endpoint"] = os.getenv("OLLAMA_ENDPOINT")

        # Knowledge settings
        if os.getenv("EMBEDDING_MODEL"):
            config_data["knowledge"]["embedding_model"] = os.getenv("EMBEDDING_MODEL")
        if os.getenv("EMBEDDING_PROVIDER"):
            config_data["knowledge"]["embedding_provider"] = os.getenv("EMBEDDING_PROVIDER")
        if os.getenv("CHUNK_SIZE"):
            config_data["knowledge"]["chunk_size"] = int(os.getenv("CHUNK_SIZE"))
        if os.getenv("CHUNK_OVERLAP"):
            config_data["knowledge"]["chunk_overlap"] = int(os.getenv("CHUNK_OVERLAP"))
        if os.getenv("OPENSEARCH_INDEX_NAME"):
            config_data["knowledge"]["index_name"] = os.getenv("OPENSEARCH_INDEX_NAME")
        if os.getenv("OCR_ENABLED"):
            config_data["knowledge"]["ocr"] = os.getenv("OCR_ENABLED").lower() in (
                "true",
                "1",
                "yes",
            )
        if os.getenv("PICTURE_DESCRIPTIONS_ENABLED"):
            config_data["knowledge"]["picture_descriptions"] = os.getenv(
                "PICTURE_DESCRIPTIONS_ENABLED"
            ).lower() in ("true", "1", "yes")

        # Agent settings
        if os.getenv("LLM_MODEL"):
            config_data["agent"]["llm_model"] = os.getenv("LLM_MODEL")
        if os.getenv("LLM_PROVIDER"):
            config_data["agent"]["llm_provider"] = os.getenv("LLM_PROVIDER")
        if os.getenv("SYSTEM_PROMPT"):
            config_data["agent"]["system_prompt"] = os.getenv("SYSTEM_PROMPT")

    def get_config(self) -> OpenRAGConfig:
        """Get current configuration, loading if necessary."""
        if self._config is None:
            return self.load_config()
        return self._config

    def reload_config(self) -> OpenRAGConfig:
        """Force reload configuration from sources."""
        self._config = None
        return self.load_config()

    def save_config_file(self, config: Optional[OpenRAGConfig] = None) -> bool:
        """Save configuration to file.

        Args:
            config: Configuration to save. If None, uses current config.

        Returns:
            True if saved successfully, False otherwise.
        """
        if config is None:
            config = self.get_config()

        # Mark config as edited when saving
        config.edited = True

        try:
            # Ensure directory exists
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_file, "w") as f:
                yaml.dump(config.to_dict(), f, default_flow_style=False, indent=2)

            # Update cached config to reflect the edited flags
            self._config = config

            logger.info(f"Configuration saved to {self.config_file} - marked as edited")
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration to {self.config_file}: {e}")
            return False

    def update_onboarding_state(self, **kwargs) -> bool:
        """Update onboarding state fields.

        Args:
            **kwargs: Onboarding state fields to update (current_step, assistant_message, etc.)

        Returns:
            True if updated successfully, False otherwise.
        """
        try:
            config = self.get_config()
            
            # Update only the provided fields
            for key, value in kwargs.items():
                if hasattr(config.onboarding, key):
                    setattr(config.onboarding, key, value)
                else:
                    logger.warning(f"Unknown onboarding field: {key}")
            
            # Save the updated config
            return self.save_config_file(config)
        except Exception as e:
            logger.error(f"Failed to update onboarding state: {e}")
            return False


# Global config manager instance
config_manager = ConfigManager()
