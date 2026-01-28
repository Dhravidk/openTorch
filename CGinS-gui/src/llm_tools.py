"""
src/llm_tools.py
Generalized LLM tooling for handling model agnostic conversations and tooling.
"""
import json
from typing import Any, Dict, List

import anthropic
from google import genai
import ollama as ol
from openai import OpenAI

from src.llm_config import resolve_llm_config


def _openai_needs_responses(model: str) -> bool:
    m = (model or "").strip().lower()
    return m.startswith("gpt-5") or m.startswith("gpt-4.1")


def _openai_response_text(resp) -> str:
    text = getattr(resp, "output_text", None)
    if text:
        return text
    try:
        for item in resp.output:
            for content in item.content:
                if getattr(content, "type", "") == "output_text":
                    return content.text
    except Exception:
        pass
    return str(resp)


def complete(system: str, user: str, provider: str | None = None, model: str | None = None) -> str:
    """Single-shot completion using the resolved provider/model."""

    cfg = resolve_llm_config(provider, model)
    prov = cfg["provider"]
    mdl = cfg["model"]

    try:
        if prov == "openai":
            if not cfg["openai_api_key"]:
                return "LLM summary unavailable: missing OPENAI_API_KEY"
            client = OpenAI(api_key=cfg["openai_api_key"], base_url=cfg["base_url"])
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            if _openai_needs_responses(mdl):
                resp = client.responses.create(model=mdl, input=messages, max_output_tokens=512)
                return _openai_response_text(resp)
            resp = client.chat.completions.create(model=mdl, messages=messages, max_tokens=512)
            return resp.choices[0].message.content

        if prov == "anthropic":
            if not cfg["anthropic_api_key"]:
                return "LLM summary unavailable: missing ANTHROPIC_API_KEY"
            client = anthropic.Anthropic(api_key=cfg["anthropic_api_key"])
            msg = client.messages.create(
                model=mdl,
                max_tokens=512,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(block.text for block in msg.content if hasattr(block, "text"))

        if prov == "gemini":
            if not cfg["google_api_key"]:
                return "LLM summary unavailable: missing GOOGLE_API_KEY"
            client = genai.Client(api_key=cfg["google_api_key"])
            resp = client.models.generate_content(
                model=mdl,
                contents=user,
                config={"system_instruction": system},
            )
            return getattr(resp, "text", str(resp))

        if prov == "ollama":
            resp = ol.chat(
                model=mdl,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            return resp["message"]["content"]

        return f"LLM summary unavailable: unsupported provider {prov}"

    except Exception as exc:
        return f"LLM summary unavailable: {exc}"


class GenModel:
    """
    Provider-agnostic chat history.

    - sys_prompt is stored separately
    - history contains only conversational turns w/ tool calls
    - tools are possible tools model can call
    """

    def __init__(self, sys_prompt: str):
        self.sys_prompt = sys_prompt
        self.history: List[Dict[str, Any]] = []
        self.tools: Dict[str, callable] = {}

    def chat(self, user_msg: str, model: str | None = None, provider: str | None = None) -> str:
        if not user_msg:
            return ""
        cfg = resolve_llm_config(provider, model)
        self.__user(user_msg)

        response = ""
        if cfg["provider"] == "openai":
            response = self.__chatgpt(cfg["model"], cfg)
        elif cfg["provider"] == "gemini":
            response = self.__gemini(cfg["model"], cfg)
        elif cfg["provider"] == "ollama":
            response = self.__ollama(cfg["model"])
        else:
            response = self.__claude(cfg["model"], cfg)

        self.__assistant(response)
        return response

    def set_sys_prompt(self, sys_prompt):
        self.sys_prompt = sys_prompt

    def set_tools(self, tools: Dict[str, callable]):
        self.tools = tools

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.history, **kwargs)

    def __repr__(self) -> str:
        return f"ChatHistory(turns={len(self.history)})"

    # Helper functions to interface with different LLM providers

    def __claude(self, model: str, cfg: Dict[str, Any]) -> str:
        """Call Anthropics's Claude API

        Args:
            model (str): Claude model name 

        Returns:
            str: LLM response
        """

        payload = self.__to_anthropic_payload()

        try:
            if not cfg.get("anthropic_api_key"):
                return "Error calling Claude API: missing ANTHROPIC_API_KEY"
            # Make the API call
            self._anthropic_client = anthropic.Anthropic(api_key=cfg["anthropic_api_key"])
            message = self._anthropic_client.messages.create(
                model=model,
                max_tokens=4096,
                system=payload["system"],
                messages=payload["messages"]
            )

            # Extract text from response
            response_text = ""
            for block in message.content:
                if hasattr(block, 'text'):
                    response_text += block.text

            return response_text

        except Exception as e:
            return f"Error calling Claude API: {str(e)}"

    def __gemini(self, model: str, cfg: Dict[str, Any]) -> str:
        """Call Google's Gemini API

        Args:
            model (str): Gemini model name 

        Returns:
            str: LLM response
        """

        try:
            if not cfg.get("google_api_key"):
                return "Error calling Gemini API: missing GOOGLE_API_KEY"
            self._genai_client = genai.Client(api_key=cfg["google_api_key"])

            # For first message, just generate content
            if len(self.history) == 1:
                response = self._genai_client.models.generate_content(
                    model=model,
                    contents=self.history[0]["content"],
                    config={
                        "system_instruction": self.sys_prompt
                    }
                )
                return response.text

            # For multi-turn conversations, use chat API
            # Convert history to Gemini format
            chat_history = []
            for msg in self.history[:-1]:  # Exclude the last user message
                role = "model" if msg["role"] == "assistant" else "user"
                chat_history.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })

            # Create chat with history
            chat = self._genai_client.chats.create(
                model=model,
                config={
                    "system_instruction": self.sys_prompt
                },
                history=chat_history
            )

            # Send the latest user message
            latest_user_msg = self.history[-1]["content"]
            response = chat.send_message(latest_user_msg)

            return response.text

        except Exception as e:
            return f"Error calling Gemini API: {str(e)}"

    def __chatgpt(self, model: str, cfg: Dict[str, Any]) -> str:
        """Call OpenAI's ChatGPT API

        Args:
            model (str): ChatGPT model name 

        Returns:
            str: LLM response
        """

        try:
            if not cfg.get("openai_api_key"):
                return "Error calling OpenAI API: missing OPENAI_API_KEY"
            self._openai_client = OpenAI(api_key=cfg["openai_api_key"], base_url=cfg.get("base_url"))
            messages = self.__to_openai_messages()
            if _openai_needs_responses(model):
                resp = self._openai_client.responses.create(
                    model=model,
                    input=messages,
                    max_output_tokens=4096,
                )
                return _openai_response_text(resp)

            # Make the API call
            response = self._openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=4096
            )
            return response.choices[0].message.content

        except Exception as e:
            return f"Error calling OpenAI API: {str(e)}"

    def __ollama(self, model: str) -> str:
        try:
            response = ol.chat(
                model=model,
                messages=self.__to_openai_messages(),
            )
            return response["message"]["content"]
        except Exception as e:
            return f"Error calling Ollama: {str(e)}"

    # Helper functions to add different types of messages to chat history

    def __user(self, content: str) -> None:
        self.history.append({"role": "user", "content": content})

    def __assistant(self, content: str) -> None:
        self.history.append({"role": "assistant", "content": content})

    def __tool(self, name: str, content: str) -> None:
        self.history.append({
            "role": "tool",
            "name": name,
            "content": content
        })

    # Helper functions to extract chat history format for generator

    def __to_openai_messages(self) -> List[Dict[str, Any]]:
        return (
            [{"role": "system", "content": self.sys_prompt}]
            + self.history
        )

    def __to_anthropic_payload(self) -> Dict[str, Any]:
        return {
            "system": self.sys_prompt,
            "messages": self.history
        }
