"""Typer CLI for the local conversation archive."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from reweave import __version__
from reweave.archive import ArchiveStore, export_conversation_markdown, export_search_markdown
from reweave.config import Config
from reweave.desktop import main as run_desktop
from reweave.web import create_app

app = typer.Typer(
    name="reweave",
    help="Local archive/search app for ChatGPT and Claude exports.",
    no_args_is_help=True,
)
console = Console()
DEFAULT_CONFIG = Config()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"reweave v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """Reweave CLI."""


@app.command("import")
def import_(
    input_dir: Annotated[
        Path, typer.Argument(help="Directory, JSON file, or zip archive to import.")
    ],
    db: Annotated[
        Path, typer.Option("--db", help="SQLite archive database.")
    ] = DEFAULT_CONFIG.db_path,
) -> None:
    """Import ChatGPT/Claude exports into a local SQLite archive."""
    store = ArchiveStore(db)
    try:
        summary = store.import_path(input_dir)
    except ValueError as exc:
        console.print(f"[red]Import failed:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]Imported archive:[/green] {db}")
    console.print(f"  Parsed conversations: {summary.parsed_conversations}")
    console.print(f"  New conversations: {summary.inserted_conversations}")
    console.print(f"  New messages: {summary.inserted_messages}")
    if summary.skipped_files:
        console.print(f"  Skipped files: {len(summary.skipped_files)}")


@app.command()
def search(
    query: Annotated[str, typer.Argument(help="Full-text search query.")],
    db: Annotated[
        Path, typer.Option("--db", help="SQLite archive database.")
    ] = DEFAULT_CONFIG.db_path,
    provider: Annotated[
        str | None, typer.Option("--provider", help="Filter by source: chatgpt or claude.")
    ] = None,
    date_from: Annotated[
        str | None, typer.Option("--from", help="Filter conversations created on/after date.")
    ] = None,
    date_to: Annotated[
        str | None, typer.Option("--to", help="Filter conversations created on/before date.")
    ] = None,
    title: Annotated[
        str | None, typer.Option("--title", help="Filter by conversation title substring.")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Maximum results.")] = 20,
) -> None:
    """Search archived conversations."""
    store = ArchiveStore(db)
    results = store.search(
        query=query,
        provider=provider,
        date_from=date_from,
        date_to=date_to,
        title=title,
        limit=limit,
    )
    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    table = Table(show_lines=True)
    table.add_column("Conversation")
    table.add_column("Idx", justify="right")
    table.add_column("Role")
    table.add_column("Excerpt")
    for result in results:
        table.add_row(
            f"{result.title}\n[dim]{result.conversation_id}[/dim]",
            str(result.message_index),
            result.role,
            result.excerpt,
        )
    console.print(table)


@app.command()
def show(
    conversation_id: Annotated[str, typer.Argument(help="Conversation ID to display.")],
    db: Annotated[
        Path, typer.Option("--db", help="SQLite archive database.")
    ] = DEFAULT_CONFIG.db_path,
) -> None:
    """Show one archived conversation with original message order."""
    store = ArchiveStore(db)
    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        console.print(f"[red]Conversation not found:[/red] {conversation_id}")
        raise typer.Exit(1)

    console.print(f"[bold]{conversation.title}[/bold]")
    console.print(
        f"[dim]{conversation.id} | {conversation.source} | {conversation.created_at}[/dim]\n"
    )
    for message in store.get_messages(conversation_id):
        stamp = f" | {message.timestamp}" if message.timestamp else ""
        console.print(f"[bold]{message.index}. {message.role}{stamp}[/bold]")
        console.print(message.content)
        console.print()


@app.command()
def stats(
    db: Annotated[
        Path, typer.Option("--db", help="SQLite archive database.")
    ] = DEFAULT_CONFIG.db_path,
) -> None:
    """Show archive statistics."""
    store = ArchiveStore(db)
    stats_data = store.stats()
    console.print("[bold]Archive Stats[/bold]")
    console.print(f"  Conversations: {stats_data.total_conversations}")
    console.print(f"  Messages: {stats_data.total_messages}")
    console.print(
        f"  Date range: {stats_data.first_created or '-'} -> {stats_data.last_created or '-'}"
    )

    if stats_data.by_source:
        table = Table(title="By Source")
        table.add_column("Source")
        table.add_column("Conversations", justify="right")
        table.add_column("Messages", justify="right")
        for row in stats_data.by_source:
            table.add_row(row.source, str(row.conversations), str(row.messages))
        console.print(table)

    if stats_data.longest_conversations:
        table = Table(title="Longest Conversations")
        table.add_column("Title")
        table.add_column("ID")
        table.add_column("Messages", justify="right")
        for row in stats_data.longest_conversations:
            table.add_row(row.title, row.id, str(row.messages))
        console.print(table)


@app.command("export")
def export_(
    conversation_id: Annotated[
        str | None, typer.Argument(help="Conversation ID to export.")
    ] = None,
    query: Annotated[
        str | None, typer.Option("--query", "-q", help="Export a search-result dossier.")
    ] = None,
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Output directory.")
    ] = DEFAULT_CONFIG.output_dir,
    db: Annotated[
        Path, typer.Option("--db", help="SQLite archive database.")
    ] = DEFAULT_CONFIG.db_path,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Maximum search results.")] = 50,
) -> None:
    """Export a conversation or search-result dossier to Markdown."""
    if conversation_id is None and query is None:
        console.print("[red]Provide a conversation_id or --query.[/red]")
        raise typer.Exit(1)
    if conversation_id is not None and query is not None:
        console.print("[red]Use either conversation_id or --query, not both.[/red]")
        raise typer.Exit(1)

    store = ArchiveStore(db)
    output.mkdir(parents=True, exist_ok=True)

    if conversation_id is not None:
        conversation = store.get_conversation(conversation_id)
        if conversation is None:
            console.print(f"[red]Conversation not found:[/red] {conversation_id}")
            raise typer.Exit(1)
        path = export_conversation_markdown(
            output, conversation, store.get_messages(conversation_id)
        )
    else:
        assert query is not None
        results = store.search(query=query, limit=limit)
        if not results:
            console.print("[yellow]No results found.[/yellow]")
            raise typer.Exit(1)
        path = export_search_markdown(output, query, results)

    console.print(f"[green]Exported:[/green] {path}")


@app.command("app")
def app_(
    db: Annotated[
        Path, typer.Option("--db", help="SQLite archive database.")
    ] = DEFAULT_CONFIG.db_path,
    host: Annotated[str, typer.Option("--host", help="Host to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Port to bind.")] = 8765,
) -> None:
    """Run the local web app."""
    import uvicorn

    static_dir = Path(__file__).parent / "web" / "dist"
    if not static_dir.exists():
        console.print("[yellow]Frontend build not found; API will still run.[/yellow]")
        static_dir = None

    console.print(f"[green]Starting Reweave app:[/green] http://{host}:{port}")
    uvicorn.run(create_app(db, static_dir=static_dir), host=host, port=port)


@app.command("desktop")
def desktop(
    db: Annotated[
        Path | None,
        typer.Option("--db", help="SQLite archive database. Defaults to Reweave app data."),
    ] = None,
) -> None:
    """Run Reweave as a desktop app window."""
    run_desktop(db)
