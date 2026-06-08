"""個人記帳 CLI 工具"""
import sqlite3
import sys
import io
import typer

# Windows 終端機 UTF-8 輸出
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime, date
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich import box

app = typer.Typer(help="個人記帳工具 - 追蹤你的收支")
console = Console()

DB_PATH = "ledger.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            date    TEXT    NOT NULL,
            type    TEXT    NOT NULL CHECK(type IN ('收入','支出')),
            amount  REAL    NOT NULL CHECK(amount > 0),
            category TEXT   NOT NULL DEFAULT '其他',
            note    TEXT    DEFAULT ''
        )
    """)
    conn.commit()
    return conn


def fmt_amount(t: str, amount: float) -> str:
    color = "green" if t == "收入" else "red"
    sign  = "+" if t == "收入" else "-"
    return f"[{color}]{sign}{amount:,.0f}[/{color}]"


# ── 新增交易 ─────────────────────────────────────────────────────────────────

@app.command("add", help="新增一筆收支紀錄")
def add(
    amount:   float = typer.Argument(..., help="金額（正數）"),
    type_:    str   = typer.Option("支出", "--type", "-t",
                                   help="收入 或 支出", show_default=True),
    category: str   = typer.Option("其他", "--cat",  "-c", help="分類"),
    note:     str   = typer.Option("",    "--note", "-n", help="備註"),
    day:      str   = typer.Option(None,  "--date", "-d",
                                   help="日期 YYYY-MM-DD，預設今天"),
):
    if type_ not in ("收入", "支出"):
        console.print("[red]--type 只能是「收入」或「支出」[/red]")
        raise typer.Exit(1)
    if amount <= 0:
        console.print("[red]金額必須大於 0[/red]")
        raise typer.Exit(1)

    entry_date = day or date.today().isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO transactions (date, type, amount, category, note) VALUES (?,?,?,?,?)",
            (entry_date, type_, amount, category, note),
        )
        console.print(
            f"[bold]已新增[/bold] #{cur.lastrowid}  "
            f"{fmt_amount(type_, amount)} 元  [{category}]  {entry_date}"
        )


# ── 列出紀錄 ─────────────────────────────────────────────────────────────────

@app.command("list", help="列出交易紀錄")
def list_records(
    month:  Optional[str] = typer.Option(None, "--month", "-m",
                                         help="篩選月份 YYYY-MM"),
    type_:  Optional[str] = typer.Option(None, "--type",  "-t",
                                         help="篩選 收入 / 支出"),
    limit:  int           = typer.Option(20,   "--limit", "-l",
                                         help="最多顯示幾筆"),
):
    query  = "SELECT id, date, type, amount, category, note FROM transactions WHERE 1=1"
    params: list = []
    if month:
        query  += " AND date LIKE ?"
        params.append(f"{month}%")
    if type_:
        query  += " AND type = ?"
        params.append(type_)
    query += " ORDER BY date DESC, id DESC LIMIT ?"
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    if not rows:
        console.print("[yellow]沒有符合條件的紀錄[/yellow]")
        return

    table = Table(box=box.SIMPLE_HEAD, show_footer=False)
    table.add_column("ID",   style="dim",   justify="right")
    table.add_column("日期",               justify="center")
    table.add_column("類型",               justify="center")
    table.add_column("金額",               justify="right")
    table.add_column("分類")
    table.add_column("備註")

    for rid, d, t, amt, cat, note in rows:
        color = "green" if t == "收入" else "red"
        sign  = "+" if t == "收入" else "-"
        table.add_row(
            str(rid), d,
            f"[{color}]{t}[/{color}]",
            f"[{color}]{sign}{amt:,.0f}[/{color}]",
            cat, note or ""
        )

    console.print(table)


# ── 月報表 ───────────────────────────────────────────────────────────────────

@app.command("report", help="顯示月收支報表")
def report(
    month: str = typer.Argument(
        None, help="月份 YYYY-MM，預設本月"
    )
):
    month = month or date.today().strftime("%Y-%m")
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT type, category, SUM(amount)
               FROM transactions
               WHERE date LIKE ?
               GROUP BY type, category
               ORDER BY type, SUM(amount) DESC""",
            (f"{month}%",),
        ).fetchall()
        totals = conn.execute(
            """SELECT type, SUM(amount)
               FROM transactions
               WHERE date LIKE ?
               GROUP BY type""",
            (f"{month}%",),
        ).fetchall()

    console.rule(f"[bold]{month} 月報表[/bold]")

    if not rows:
        console.print("[yellow]本月暫無紀錄[/yellow]")
        return

    table = Table(box=box.SIMPLE_HEAD)
    table.add_column("類型", justify="center")
    table.add_column("分類")
    table.add_column("小計", justify="right")

    for t, cat, amt in rows:
        color = "green" if t == "收入" else "red"
        table.add_row(
            f"[{color}]{t}[/{color}]",
            cat,
            f"[{color}]{amt:,.0f}[/{color}]",
        )

    console.print(table)

    income  = next((s for tp, s in totals if tp == "收入"), 0)
    expense = next((s for tp, s in totals if tp == "支出"), 0)
    balance = income - expense
    bal_color = "green" if balance >= 0 else "red"

    console.print(f"  收入合計: [green]{income:>12,.0f}[/green]")
    console.print(f"  支出合計: [red]{expense:>12,.0f}[/red]")
    console.print(f"  結餘:     [{bal_color}]{balance:>12,.0f}[/{bal_color}]")


# ── 刪除紀錄 ─────────────────────────────────────────────────────────────────

@app.command("delete", help="刪除一筆紀錄（依 ID）")
def delete(id_: int = typer.Argument(..., help="交易 ID")):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM transactions WHERE id=?", (id_,)).fetchone()
        if not row:
            console.print(f"[red]找不到 ID={id_} 的紀錄[/red]")
            raise typer.Exit(1)
        typer.confirm(f"確定刪除 ID={id_}？", abort=True)
        conn.execute("DELETE FROM transactions WHERE id=?", (id_,))
        console.print(f"[dim]已刪除 ID={id_}[/dim]")


if __name__ == "__main__":
    app()
