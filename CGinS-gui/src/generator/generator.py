"""
src/generator/generator.py
Uses LLM to generate CUDA kernels that is semi-model-agnostic.
"""
import re

from google import genai
import ollama as ol
from anthropic import Anthropic
from openai import OpenAI

import src.generator.prompts.prompts
from src.llm_config import resolve_llm_config


def cleanup_mkdown(input: str) -> str:
    """Extract code from markdown code blocks using regex."""

    # Try to match code blocks with language specifiers (C++, cpp, cuda, c)
    pattern = r"```(?:C\+\+|cpp|cuda|c)\s*\n(.*?)```"
    match = re.search(pattern, input, re.DOTALL | re.IGNORECASE)

    if match:
        return match.group(1).strip()

    # Try generic code block without language specifier
    pattern = r"```\s*\n(.*?)```"
    match = re.search(pattern, input, re.DOTALL)

    if match:
        return match.group(1).strip()

    # No markdown found, return as-is
    return input.strip()


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


def _openai_needs_responses(model: str) -> bool:
    m = (model or "").strip().lower()
    return m.startswith("gpt-5") or m.startswith("gpt-4.1")


def _openai_responses_generate(client: OpenAI, messages: list, model: str) -> str:
    resp = client.responses.create(
        model=model,
        input=messages,
        max_output_tokens=4096,
    )
    return cleanup_mkdown(_openai_response_text(resp))


def ollama_generator(msg: str, model: str = "llama3.2:latest", outputIR: str = "CUDA") -> str:
    """Initial generation of kernel/IR

    Args:
        msg (str): Context for LLM to generate Kernel/IR
        model (str, optional): Which Ollama model to use for LLM. Defaults to "llama3.2:latest".
        outputIR (str, optional): What is the desired output IR type. Defaults to "CUDA".

    Returns:
        str: kernel_code
    """
    cfg = resolve_llm_config("ollama", model)
    print("Generating code...")
    sys_prompt = src.generator.prompts.prompts.get_system_prompt()
    response = ol.chat(model=model, messages=[
                       {"role": "system", "content": sys_prompt}, {"role": "user", "content": msg}])

    cu_code = response['message']['content']

    print("Code generated...")
    return cleanup_mkdown(cu_code)


def convert_chatgpt_to_gemini(chatgpt_history: list) -> list:
    gemini_history = []

    for msg in chatgpt_history:
        role = msg["role"]

        # Gemini uses "model" instead of "assistant"
        if role == "assistant":
            role = "model"

        # Gemini supports only "user" and "model" inside the messages list
        if role == "system":
            # Skip it here (it goes to system_instruction)
            continue

        content = msg["content"]
        gemini_history.append({
            "role": role,
            "parts": [content]
        })

    return gemini_history


def gemini_generator(conversation_history: list, model: str = "gemini-2.5-flash", outputIR: str = "CUDA") -> str:
    """Kernel generation using the **google-genai** client.

    The repository depends on the `google-genai` package. Its API differs from the
    older `google.generativeai` SDK, so we use `genai.Client()` here (same pattern
    as src/llm_tools.py).
    """

    print("Generating code (Gemini)...")
    sys_prompt = src.generator.prompts.prompts.get_system_prompt()

    cfg = resolve_llm_config("gemini", model)
    if not cfg.get("google_api_key"):
        raise RuntimeError("GOOGLE_API_KEY is required for Gemini provider")
    client = genai.Client(api_key=cfg["google_api_key"])

    # Single turn case
    if len(conversation_history) <= 1:
        user_msg = conversation_history[0]["content"] if conversation_history else ""
        response = client.models.generate_content(
            model=model,
            contents=user_msg,
            config={"system_instruction": sys_prompt},
        )
        return cleanup_mkdown(getattr(response, "text", str(response)))

    # Multi-turn chat
    chat_history = []
    for msg in conversation_history[:-1]:
        role = "model" if msg.get("role") == "assistant" else "user"
        chat_history.append({"role": role, "parts": [{"text": msg.get("content", "")}]} )

    chat = client.chats.create(
        model=model,
        config={"system_instruction": sys_prompt},
        history=chat_history,
    )

    latest = conversation_history[-1].get("content", "")
    response = chat.send_message(latest)
    return cleanup_mkdown(getattr(response, "text", str(response)))


def chatgpt_generator(conversation_history: list, model: str = "gpt-4o", outputIR: str = "CUDA") -> str:
    """Initial generation of kernel/IR using OpenAI.

    Returns:
        str: kernel_code
    """

    cfg = resolve_llm_config("openai", model)
    if not cfg.get("openai_api_key"):
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI provider")
    client = OpenAI(api_key=cfg["openai_api_key"], base_url=cfg.get("base_url"))

    print("Generating code (OpenAI)...")
    sys_prompt = src.generator.prompts.prompts.get_system_prompt()

    # Do NOT mutate caller's list; OpenAI expects explicit system message objects.
    messages = [{"role": "system", "content": sys_prompt}] + list(conversation_history)

    if _openai_needs_responses(model):
        cu_code = _openai_responses_generate(client, messages, model)
        print("Code generated...")
        return cu_code

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=4096,
        )
        cu_code = cleanup_mkdown(response.choices[0].message.content)
        print("Code generated...")
        return cu_code
    except Exception as exc:
        if "v1/responses" in str(exc):
            cu_code = _openai_responses_generate(client, messages, model)
            print("Code generated...")
            return cu_code
        raise


def convert_chatgpt_to_anthropic(chatgpt_history: list) -> list:
    anthropic_history = []
    for msg in chatgpt_history:
        role = msg["role"]
        if role == "system":
            continue  # Handle separately
        if role == "assistant":
            role = "assistant"
        elif role == "user":
            role = "user"

        content = msg["content"]
        anthropic_history.append({
            "role": role,
            "content": content
        })
    return anthropic_history


def anthropic_generator(conversation_history: list,
                        model: str = "claude-opus-4-5-20251101") -> str:
    """Initial generation of kernel/IR using Anthropic Claude API."""
    print("Generating code with Claude...")

    from anthropic import Anthropic

    anthropic_history = convert_chatgpt_to_anthropic(conversation_history)

    cfg = resolve_llm_config("anthropic", model)
    if not cfg.get("anthropic_api_key"):
        raise RuntimeError("ANTHROPIC_API_KEY is required for Anthropic provider")
    client = Anthropic(api_key=cfg["anthropic_api_key"])

    # Build the request parameters
    params = {
        "model": model,
        "max_tokens": 4096,
        "system": src.generator.prompts.prompts.get_system_prompt(),
        "messages": anthropic_history
    }

    response = client.messages.create(**params)

    # Extract the generated content
    code = cleanup_mkdown(response.content[0].text)

    print("Code generated…")
    return code
