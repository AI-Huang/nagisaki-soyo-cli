from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .chatbot import ChatSession, OPENAI_ERRORS
from .config import DEFAULT_MODEL, DEFAULT_TEMPERATURE
from .mysql_profile_source import load_mysql_profile_source
from .profile_analysis import analyze_user_language, format_analysis_summary, load_text_samples, save_analysis_result
from .prompts import DEFAULT_SYSTEM_PROMPT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nagisaki-soyo-cli",
        description="LangChain-based command-line chatbot with a gentle Soyo persona.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name for the OpenAI-compatible API.")
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Sampling temperature for responses.",
    )
    parser.add_argument(
        "--system-prompt-file",
        type=Path,
        help="Optional file that replaces the built-in system prompt.",
    )
    parser.add_argument("--prompt", help="Send one message and print one reply without entering the REPL.")
    parser.add_argument(
        "--save-on-exit",
        action="store_true",
        help="Save the conversation transcript when leaving the chat.",
    )
    parser.add_argument("--no-banner", action="store_true", help="Do not print the startup banner.")
    return parser


def build_profile_analyze_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nagisaki-soyo-cli profile-analyze",
        description="Analyze user texts and build an agent-persona reference scaffold.",
    )
    parser.add_argument("--user-name", required=True, help="Display name for the analyzed user.")
    parser.add_argument(
        "--input-file",
        type=Path,
        required=True,
        help="Input .json, .jsonl, or .txt file containing the user's texts.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Optional output JSON path. Defaults to data/profile_runs/<timestamp>-<user>.json.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use the configured OpenAI-compatible LLM to generate the persona summary.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name for optional LLM summarization.")
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Sampling temperature for optional LLM summarization.",
    )
    return parser


def build_profile_analyze_mysql_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nagisaki-soyo-cli profile-analyze-mysql",
        description="Analyze a user's texts directly from the local xhs_crawler MySQL database.",
    )
    parser.add_argument("--user-name", help="Display name to match against users.nickname or authors.author_name.")
    parser.add_argument("--user-id", help="Exact user identifier from xhs_crawler.users.")
    parser.add_argument(
        "--max-notes",
        type=int,
        default=50,
        help="Maximum number of notes to load from MySQL.",
    )
    parser.add_argument(
        "--max-comments",
        type=int,
        default=50,
        help="Maximum number of comments to load from MySQL.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Optional output JSON path. Defaults to data/profile_runs/<timestamp>-<user>.json.",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="Use the configured OpenAI-compatible LLM to generate the persona summary.",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name for optional LLM summarization.")
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="Sampling temperature for optional LLM summarization.",
    )
    return parser


def load_system_prompt(path: Path | None) -> str:
    if path is None:
        return DEFAULT_SYSTEM_PROMPT
    return path.read_text(encoding="utf-8").strip()


def print_banner() -> None:
    print("Soyo is ready. Type /help for commands.")


def print_help() -> None:
    print("/help  show commands")
    print("/reset clear conversation history")
    print("/save  save transcript to data/transcripts/")
    print("/exit  leave the chat")


def run_repl(session: ChatSession, save_on_exit: bool) -> None:
    while True:
        try:
            user_text = input("you> ").strip()
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except EOFError:
            print()
            break

        if not user_text:
            continue
        if user_text in {"/exit", "/quit"}:
            break
        if user_text == "/help":
            print_help()
            continue
        if user_text == "/reset":
            session.reset()
            print("Conversation cleared.")
            continue
        if user_text == "/save":
            path = session.save_transcript()
            print(f"Saved transcript to {path}.")
            continue

        try:
            reply = session.reply(user_text)
        except OPENAI_ERRORS as exc:
            print(f"Model request failed: {exc}")
            continue
        print(f"soyo> {reply}")

    if save_on_exit and session.messages:
        path = session.save_transcript()
        print(f"Saved transcript to {path}.")


def main() -> None:
    argv = sys.argv[1:]
    if argv and argv[0] == "profile-analyze":
        parser = build_profile_analyze_parser()
        args = parser.parse_args(argv[1:])
        samples = load_text_samples(args.input_file)
        result = analyze_user_language(
            user_name=args.user_name,
            samples=samples,
            use_llm=args.use_llm,
            model=args.model,
            temperature=args.temperature,
        )
        path = save_analysis_result(result, args.output_file)
        print(format_analysis_summary(result))
        print(f"saved_profile: {path}")
        return
    if argv and argv[0] == "profile-analyze-mysql":
        parser = build_profile_analyze_mysql_parser()
        args = parser.parse_args(argv[1:])
        if not args.user_name and not args.user_id:
            raise SystemExit("profile-analyze-mysql requires --user-name or --user-id.")
        source = load_mysql_profile_source(
            user_name=args.user_name,
            user_id=args.user_id,
            max_notes=args.max_notes,
            max_comments=args.max_comments,
        )
        result = analyze_user_language(
            user_name=source.user_name,
            samples=source.samples,
            use_llm=args.use_llm,
            model=args.model,
            temperature=args.temperature,
        )
        path = save_analysis_result(result, args.output_file)
        print(format_analysis_summary(result))
        print(f"mysql_user_id: {source.user_id}")
        print(f"saved_profile: {path}")
        return

    parser = build_parser()
    args = parser.parse_args(argv)
    system_prompt = load_system_prompt(args.system_prompt_file)
    session = ChatSession(
        model=args.model,
        temperature=args.temperature,
        system_prompt=system_prompt,
    )

    if args.prompt:
        try:
            reply = session.reply(args.prompt)
        except OPENAI_ERRORS as exc:
            raise SystemExit(f"Model request failed: {exc}") from exc
        print(reply)
        if args.save_on_exit:
            path = session.save_transcript()
            print(f"Saved transcript to {path}.")
        return

    if not args.no_banner:
        print_banner()
    run_repl(session, save_on_exit=args.save_on_exit)
