"""
Quick Diagnostic Test Script for Angel One SmartAPI Connection.
Verifies login, TOTP handshake, user profile, and available trading margin.
"""
import sys
from brokers.angelone_adapter import AngelOneBroker
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def test_connection():
    console.print(Panel("[bold cyan]Angel One SmartAPI Authentication Test[/bold cyan]", border_style="cyan"))
    
    broker = AngelOneBroker()
    console.print(f"Client Code: [bold]{broker.client_code}[/bold]")
    console.print(f"API Key: [bold]{broker.api_key[:4]}****[/bold]")
    console.print("Generating TOTP & Authenticating session...")
    
    success = broker.connect()
    if not success:
        console.print("[bold red]❌ Authentication Failed.[/bold red]")
        console.print("[yellow]Tips:[/yellow]")
        console.print("1. Ensure this command is run with network access or outside sandbox.")
        console.print("2. Ensure your static IP whitelisted in Angel One matches your current IP.")
        return False
        
    console.print("[bold green]✓ Authentication Successful![/bold green]")
    
    # Try fetching RMS Limits (Funds)
    try:
        rms = broker.smart_api.rmsLimit()
        if rms.get("status") and "data" in rms:
            data = rms["data"]
            table = Table(title="💰 Available Account Funds & Margin", border_style="green")
            table.add_column("Parameter", style="cyan")
            table.add_column("Value (₹)", style="bold white")
            table.add_row("Net Available Margin", f"₹{float(data.get('net', 0)):,.2f}")
            table.add_row("Available Cash", f"₹{float(data.get('availablecash', 0)):,.2f}")
            table.add_row("Collateral / Margin Used", f"₹{float(data.get('utilisedamount', 0)):,.2f}")
            console.print(table)
    except Exception as e:
        console.print(f"[yellow]Notice: Could not fetch RMS limits ({e})[/yellow]")
        
    return True

if __name__ == "__main__":
    test_connection()
