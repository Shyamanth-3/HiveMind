from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """
    Abstract base class for all LLM providers.

    Every LLM implementation (Groq, NVIDIA, OpenAI, Ollama, etc.)
    must implement this interface.
    """

    @abstractmethod
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """
        Generate a response from the language model.

        Args:
            system_prompt: Defines the assistant's role and behavior.
            user_prompt: The user's request or task.

        Returns:
            The generated text response.
        """
        pass