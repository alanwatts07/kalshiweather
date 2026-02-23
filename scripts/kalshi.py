#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "cryptography>=42.0.0",
#     "httpx>=0.27.0",
# ]
# ///
"""
Kalshi weather prediction market trading CLI.

Defaults to PAPER mode ($1000 virtual balance). Use --live for real trading.

Usage:
    uv run scripts/kalshi.py <command> [options]

Commands:
    markets              List available weather markets
    market TICKER        Market detail + orderbook
    balance              Portfolio balance (paper or live)
    positions            Current positions + P&L
    edge CITY            GFS ensemble edge detection for a city
    scan                 Scan all cities for edge opportunities
    auto                 Scan all cities + auto-buy edges (Kelly sized)
    buy TICKER SIDE AMT  Place buy order (SIDE: yes/no, AMT: dollars)
    sell TICKER SIDE AMT Sell/close position
    auto-settle          Auto-settle paper positions via Kalshi API
    settle TICKER W/L    Settle paper position (won/lost)
    history              Trade history (paper or live)
    reset                Reset paper trading account to $1000
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Add parent dir to path so we can import lib/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.config import CITIES, is_demo
from lib.positions import PositionStore
from lib.weather import EdgeOpportunity, calculate_edges, fetch_ensemble


def _get_client():
    """Lazy import + create client only when needed."""
    from lib.client import KalshiClient
    return KalshiClient.from_env()


def _banner(live: bool) -> str:
    if not live:
        return "[PAPER TRADING] Virtual $1000 account — no real money"
    if is_demo():
        return "[DEMO MODE] Trading on Kalshi demo environment"
    return "[PRODUCTION] Trading on Kalshi LIVE environment"


def _print(data: object, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)


# --- Command handlers ---


def cmd_markets(args: argparse.Namespace) -> None:
    """List available weather markets."""
    print(_banner(args.live))
    client = _get_client()

    all_markets = []
    for city in CITIES.values():
        try:
            resp = client.get_markets(series_ticker=city.series_ticker)
            markets = resp.get("markets", [])
            all_markets.extend(markets)
        except Exception as e:
            print(f"  Error fetching {city.code}: {e}", file=sys.stderr)

    if args.json:
        _print(all_markets, as_json=True)
        return

    if not all_markets:
        print("No open weather markets found.")
        return

    print(f"\n{'Ticker':<35} {'Title':<50} {'Yes':>5} {'No':>5} {'Vol':>8}")
    print("-" * 105)
    for m in all_markets:
        ticker = m.get("ticker", "")
        title = m.get("title", "")[:48]
        yes_price = m.get("yes_ask", m.get("last_price", "–"))
        no_price = m.get("no_ask", "–")
        volume = m.get("volume", 0)
        print(f"{ticker:<35} {title:<50} {yes_price:>5} {no_price:>5} {volume:>8}")


def cmd_market(args: argparse.Namespace) -> None:
    """Show market detail + orderbook."""
    print(_banner(args.live))
    client = _get_client()

    market = client.get_market(args.ticker)
    orderbook = client.get_orderbook(args.ticker)

    if args.json:
        _print({"market": market, "orderbook": orderbook}, as_json=True)
        return

    m = market.get("market", market)
    print(f"\nTicker:  {m.get('ticker', '')}")
    print(f"Title:   {m.get('title', '')}")
    print(f"Status:  {m.get('status', '')}")
    print(f"Yes Ask: {m.get('yes_ask', '–')}¢")
    print(f"No Ask:  {m.get('no_ask', '–')}¢")
    print(f"Last:    {m.get('last_price', '–')}¢")
    print(f"Volume:  {m.get('volume', 0)}")

    ob = orderbook.get("orderbook", orderbook)
    print(f"\nOrderbook:")
    yes_bids = ob.get("yes", [])
    no_bids = ob.get("no", [])
    if yes_bids:
        print(f"  YES: {yes_bids[:5]}")
    if no_bids:
        print(f"  NO:  {no_bids[:5]}")


def cmd_balance(args: argparse.Namespace) -> None:
    """Show portfolio balance."""
    print(_banner(args.live))

    if not args.live:
        store = PositionStore.load()
        open_pos = store.open_positions()
        open_cost = sum(p.cost_cents for p in open_pos if p.mode == "paper")
        print(f"\nPaper Trading Account")
        print(f"  Cash:       ${store.paper_balance_cents / 100:.2f}")
        print(f"  In trades:  ${open_cost / 100:.2f}")
        print(f"  Equity:     ${store.paper_equity_cents / 100:.2f}")
        print(f"  Total P&L:  ${store.paper_pnl_cents / 100:+.2f}")
        print(f"  Realized:   ${store.realized_pnl_cents / 100:+.2f}")
        return

    client = _get_client()
    resp = client.get_balance()
    if args.json:
        _print(resp, as_json=True)
        return
    balance_cents = resp.get("balance", 0)
    print(f"\nBalance: ${balance_cents / 100:.2f}")


def cmd_positions(args: argparse.Namespace) -> None:
    """Show current positions + P&L."""
    print(_banner(args.live))
    store = PositionStore.load()

    if not args.live:
        open_pos = [p for p in store.open_positions() if p.mode == "paper"]
        closed_pos = [p for p in store.closed_positions() if p.mode == "paper"]

        if args.json:
            _print({
                "open": [_pos_dict(p) for p in open_pos],
                "closed": [_pos_dict(p) for p in closed_pos[-10:]],
                "balance_cents": store.paper_balance_cents,
                "pnl_cents": store.paper_pnl_cents,
            }, as_json=True)
            return

        if open_pos:
            print(f"\nOpen Paper Positions:")
            print(f"  {'Ticker':<35} {'Side':<5} {'Qty':>5} {'Price':>6} {'Cost':>8}")
            print(f"  {'-'*61}")
            for p in open_pos:
                cost = p.contracts * p.avg_price_cents / 100
                print(f"  {p.ticker:<35} {p.side:<5} {p.contracts:>5} {p.avg_price_cents:>5}¢ ${cost:>7.2f}")
        else:
            print("\nNo open paper positions.")

        if closed_pos:
            print(f"\nRecent Closed (last 10):")
            for p in closed_pos[-10:]:
                pnl = p.pnl_cents or 0
                sign = "+" if pnl >= 0 else ""
                print(f"  {p.ticker}  {p.side}  {p.contracts}x  {p.avg_price_cents}¢→{p.close_price_cents}¢  {sign}${pnl/100:.2f}")

        print(f"\nPaper Balance: ${store.paper_balance_cents/100:.2f}  |  P&L: ${store.paper_pnl_cents/100:+.2f}")
        return

    # Live mode
    client = _get_client()
    resp = client.get_positions()
    positions = resp.get("market_positions", [])

    if args.json:
        _print(positions, as_json=True)
        return

    if positions:
        print(f"\n{'Ticker':<35} {'Side':<6} {'Qty':>6} {'Avg':>6}")
        print("-" * 55)
        for p in positions:
            ticker = p.get("ticker", "")
            qty = p.get("total_traded", p.get("position", 0))
            side = "yes" if qty >= 0 else "no"
            avg = p.get("average_price", "–")
            print(f"{ticker:<35} {side:<6} {abs(qty):>6} {avg:>6}¢")
    else:
        print("\nNo live positions.")


def cmd_edge(args: argparse.Namespace) -> None:
    """GFS ensemble edge detection for a city."""
    city_code = args.city.upper()
    if city_code not in CITIES:
        print(f"Unknown city: {city_code}. Available: {', '.join(CITIES.keys())}", file=sys.stderr)
        sys.exit(1)

    city = CITIES[city_code]
    dates = [date.today(), date.today() + timedelta(days=1)]
    balance = _get_balance(args.live)

    # Fetch all markets once
    all_markets = []
    try:
        client = _get_client()
        resp = client.get_markets(series_ticker=city.series_ticker)
        all_markets = resp.get("markets", [])
    except Exception as e:
        print(f"(Could not fetch market prices: {e})")
        print("Showing forecast probabilities only (no edge calculation).")

    for target in dates:
        print(f"\nFetching GFS ensemble forecast for {city.name} ({target})...")
        forecast = fetch_ensemble(city, target)
        print(f"  Ensemble members: {forecast.count}")
        print(f"  Mean high: {forecast.mean:.1f}°F")
        print(f"  Spread: {forecast.spread:.1f}°F (min={min(forecast.members):.1f}, max={max(forecast.members):.1f})")
        if forecast.bias_applied:
            print(f"  Bias correction: {forecast.bias_shift:+.1f}°F (applied)")
        else:
            print(f"  Bias correction: none (raw GFS)")

        # Build probability distribution at common thresholds
        thresholds = list(range(int(min(forecast.members)) - 5, int(max(forecast.members)) + 10, 5))

        print(f"\n{'Threshold':<12} {'P(>=)':>8} {'P(<)':>8}")
        print("-" * 30)
        for t in thresholds:
            p_above = forecast.probability_above(t)
            print(f"  {t}°F{'':<6} {p_above:>7.1%} {1-p_above:>7.1%}")

        if all_markets:
            market_prices = _markets_to_prices(all_markets, target_date=target)
            if market_prices:
                edges = calculate_edges(forecast, market_prices, balance)
                _print_edges(edges, args.json)
            else:
                print(f"\nNo markets for {city.series_ticker} on {target}")
        else:
            print(f"\nNo open markets found for {city.series_ticker}")


def cmd_scan(args: argparse.Namespace) -> None:
    """Scan all cities for edge opportunities."""
    print(_banner(args.live))
    dates = [date.today(), date.today() + timedelta(days=1)]
    all_edges: list[EdgeOpportunity] = []
    balance = _get_balance(args.live)

    try:
        client = _get_client()
    except Exception as e:
        print(f"Could not connect to Kalshi: {e}", file=sys.stderr)
        print("Showing forecasts only.\n")
        client = None

    for code, city in CITIES.items():
        # Fetch all markets for this city once
        all_markets = []
        if client:
            try:
                resp = client.get_markets(series_ticker=city.series_ticker)
                all_markets = resp.get("markets", [])
            except Exception as e:
                print(f"  Error fetching markets for {code}: {e}", file=sys.stderr)

        for target in dates:
            print(f"\n--- {city.name} ({code}) — {target} ---")
            try:
                forecast = fetch_ensemble(city, target)
                bias_tag = f"bias={forecast.bias_shift:+.1f}F" if forecast.bias_applied else "raw"
                print(f"  Members: {forecast.count} | Mean: {forecast.mean:.1f}°F | Spread: {forecast.spread:.1f}°F | {bias_tag}")

                if all_markets:
                    market_prices = _markets_to_prices(all_markets, target_date=target)

                    if market_prices:
                        edges = calculate_edges(forecast, market_prices, balance)
                        all_edges.extend(edges)
                        if edges:
                            for e in edges:
                                print(f"  EDGE: {e.ticker} {e.side} | ens={e.ensemble_prob:.1%} mkt={e.market_price:.0f}¢ edge={e.edge_pct:+.1f}%")
                        else:
                            print(f"  No edges for {code} on {target}")
                    else:
                        print(f"  No markets for {city.series_ticker} on {target}")
            except Exception as e:
                print(f"  Error: {e}")

    if all_edges:
        all_edges.sort(key=lambda e: e.edge_pct, reverse=True)
        print(f"\n=== TOP OPPORTUNITIES ===")
        print(f"{'Ticker':<35} {'Side':<5} {'Ens%':>6} {'Mkt¢':>6} {'Edge%':>7} {'Ctrs':>5}")
        print("-" * 66)
        for e in all_edges[:10]:
            print(f"{e.ticker:<35} {e.side:<5} {e.ensemble_prob:>5.1%} {e.market_price:>5.0f}¢ {e.edge_pct:>+6.1f}% {e.suggested_contracts:>5}")
    else:
        print("\nNo edges found across any city.")

    if args.json:
        _print([vars(e) for e in all_edges], as_json=True)


def cmd_buy(args: argparse.Namespace) -> None:
    """Place a buy order (paper or live)."""
    print(_banner(args.live))

    ticker = args.ticker
    side = args.side.lower()
    amount_dollars = float(args.amount)

    if side not in ("yes", "no"):
        print("Side must be 'yes' or 'no'", file=sys.stderr)
        sys.exit(1)

    # Get price — either from market or user-specified
    price = args.price
    if price is None:
        try:
            client = _get_client()
            market = client.get_market(ticker)
            m = market.get("market", market)
            if side == "yes":
                price = m.get("yes_ask", m.get("last_price", 50))
            else:
                price = m.get("no_ask", 100 - m.get("yes_ask", m.get("last_price", 50)))
        except Exception as e:
            print(f"Could not fetch price: {e}", file=sys.stderr)
            print("Use --price CENTS to specify manually for paper trading.", file=sys.stderr)
            sys.exit(1)

    if not price or price <= 0:
        print(f"Invalid price: {price}¢", file=sys.stderr)
        sys.exit(1)

    contracts = int(amount_dollars / (price / 100.0))
    if contracts <= 0:
        print(f"Amount ${amount_dollars} too small for price {price}¢", file=sys.stderr)
        sys.exit(1)

    cost = contracts * price / 100.0

    if not args.live:
        # Paper trading
        store = PositionStore.load()
        try:
            pos = store.paper_buy(ticker, side, contracts, price)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"\n[PAPER] Bought {contracts} contracts of {ticker} {side.upper()} @ {price}¢ = ${cost:.2f}")
        print(f"  Remaining balance: ${store.paper_balance_cents/100:.2f}")

        if args.json:
            _print(_pos_dict(pos), as_json=True)
        return

    # Live trading
    client = _get_client()
    print(f"\nBuying {contracts} contracts of {ticker} {side.upper()} @ {price}¢ = ${cost:.2f}")

    resp = client.create_order(ticker=ticker, side=side, action="buy", count=contracts)
    order = resp.get("order", resp)
    print(f"Order ID: {order.get('order_id', 'N/A')}")
    print(f"Status:   {order.get('status', 'submitted')}")

    store = PositionStore.load()
    store.open_position(ticker, side, contracts, price)

    if args.json:
        _print(resp, as_json=True)


def cmd_sell(args: argparse.Namespace) -> None:
    """Sell/close a position (paper or live)."""
    print(_banner(args.live))

    ticker = args.ticker
    side = args.side.lower()

    if side not in ("yes", "no"):
        print("Side must be 'yes' or 'no'", file=sys.stderr)
        sys.exit(1)

    # Get price
    price = args.price
    if price is None:
        try:
            client = _get_client()
            market = client.get_market(ticker)
            m = market.get("market", market)
            if side == "yes":
                price = m.get("yes_bid", m.get("last_price", 50))
            else:
                price = m.get("no_bid", 100 - m.get("yes_bid", m.get("last_price", 50)))
        except Exception as e:
            print(f"Could not fetch price: {e}", file=sys.stderr)
            print("Use --price CENTS to specify manually for paper trading.", file=sys.stderr)
            sys.exit(1)

    if not args.live:
        store = PositionStore.load()
        pos = store.paper_sell(ticker, side, price)
        if not pos:
            print(f"No open paper position for {ticker} {side}", file=sys.stderr)
            sys.exit(1)

        pnl = pos.pnl_cents or 0
        print(f"\n[PAPER] Sold {pos.contracts} contracts of {ticker} {side.upper()} @ {price}¢")
        print(f"  P&L: ${pnl/100:+.2f}")
        print(f"  Balance: ${store.paper_balance_cents/100:.2f}")

        if args.json:
            _print(_pos_dict(pos), as_json=True)
        return

    # Live trading
    amount_dollars = float(args.amount) if args.amount else 0
    client = _get_client()
    contracts = int(amount_dollars / (price / 100.0)) if price > 0 and amount_dollars > 0 else 0
    if contracts <= 0:
        print(f"Cannot sell: price={price}¢, amount=${amount_dollars}", file=sys.stderr)
        sys.exit(1)

    print(f"\nSelling {contracts} contracts of {ticker} {side.upper()} @ {price}¢")
    resp = client.create_order(ticker=ticker, side=side, action="sell", count=contracts)
    order = resp.get("order", resp)
    print(f"Order ID: {order.get('order_id', 'N/A')}")

    store = PositionStore.load()
    store.close_position(ticker, side, price)

    if args.json:
        _print(resp, as_json=True)


def cmd_auto_settle(args: argparse.Namespace) -> None:
    """Auto-settle paper positions using Kalshi API market results."""
    if args.live:
        print("Auto-settle is only for paper trading. Live positions settle via Kalshi.", file=sys.stderr)
        sys.exit(1)

    store = PositionStore.load()
    open_pos = [p for p in store.open_positions() if p.mode == "paper"]

    if not open_pos:
        print("No open paper positions to settle.")
        return

    client = _get_client()
    settled = 0

    for pos in open_pos:
        try:
            resp = client.get_market(pos.ticker)
            m = resp.get("market", resp)
            status = m.get("status", "")
            result = m.get("result", "")

            if status not in ("determined", "finalized"):
                print(f"  {pos.ticker}: not settled yet (status={status}), skipping")
                continue

            won = pos.side == result
            outcome_str = "WON" if won else "LOST"
            store.paper_settle(pos.ticker, won)

            payout = pos.contracts * 100 if won else 0
            cost = pos.contracts * pos.avg_price_cents
            pnl = payout - cost
            print(f"  {pos.ticker} {pos.side.upper()}: Kalshi={result} → {outcome_str} (P&L: ${pnl/100:+.2f})")
            settled += 1
        except Exception as e:
            print(f"  {pos.ticker}: error fetching market — {e}", file=sys.stderr)

    print(f"\nSettled {settled}/{len(open_pos)} positions. Balance: ${store.paper_balance_cents/100:.2f}")

    _write_status({
        "command": "auto-settle",
        "timestamp": datetime.utcnow().isoformat(),
        "mode": "paper",
        "balance_cents": store.paper_balance_cents,
        "settled": settled,
        "total_positions": len(open_pos),
        "open_positions": len(store.open_positions()),
        "total_pnl_cents": store.paper_pnl_cents,
    })


def cmd_auto(args: argparse.Namespace) -> None:
    """Scan all cities and auto-buy every edge above threshold using Kelly sizing."""
    print(_banner(args.live))
    dates = [date.today(), date.today() + timedelta(days=1)]
    balance = _get_balance(args.live)
    store = PositionStore.load()

    try:
        client = _get_client()
    except Exception as e:
        print(f"Could not connect to Kalshi: {e}", file=sys.stderr)
        sys.exit(1)

    trades = []
    edges_found = 0
    skipped_existing = 0
    skipped_error = 0

    # Build set of existing positions for dedup: (ticker, side)
    existing = {(p.ticker, p.side) for p in store.open_positions()}

    for code, city in CITIES.items():
        all_markets = []
        try:
            resp = client.get_markets(series_ticker=city.series_ticker)
            all_markets = resp.get("markets", [])
        except Exception as e:
            print(f"  Error fetching markets for {code}: {e}", file=sys.stderr)
            continue

        for target in dates:
            try:
                forecast = fetch_ensemble(city, target)
                market_prices = _markets_to_prices(all_markets, target_date=target)
                if not market_prices:
                    continue

                edges = calculate_edges(forecast, market_prices, balance)
                edges_found += len(edges)

                for edge in edges:
                    if (edge.ticker, edge.side) in existing:
                        print(f"  SKIP (held): {edge.ticker} {edge.side}")
                        skipped_existing += 1
                        continue

                    if edge.suggested_contracts <= 0:
                        continue

                    price = int(edge.market_price)
                    try:
                        if args.live:
                            client.create_order(
                                ticker=edge.ticker,
                                side=edge.side,
                                action="buy",
                                count=edge.suggested_contracts,
                            )
                            store.open_position(edge.ticker, edge.side, edge.suggested_contracts, price)
                        else:
                            store.paper_buy(edge.ticker, edge.side, edge.suggested_contracts, price)

                        existing.add((edge.ticker, edge.side))
                        trade_info = {
                            "ticker": edge.ticker,
                            "side": edge.side,
                            "contracts": edge.suggested_contracts,
                            "price": price,
                            "edge_pct": round(edge.edge_pct, 1),
                        }
                        trades.append(trade_info)
                        print(f"  BUY: {edge.ticker} {edge.side} x{edge.suggested_contracts} @ {price}¢ (edge={edge.edge_pct:+.1f}%)")
                    except Exception as e:
                        print(f"  ERROR buying {edge.ticker}: {e}", file=sys.stderr)
                        skipped_error += 1

            except Exception as e:
                print(f"  Error processing {code} {target}: {e}", file=sys.stderr)

    # Reload store to get updated balance
    store = PositionStore.load()
    open_pos = store.open_positions()

    # Summary
    print(f"\n=== AUTO-TRADE SUMMARY ===")
    print(f"  Edges found:    {edges_found}")
    print(f"  Trades placed:  {len(trades)}")
    print(f"  Skipped (held): {skipped_existing}")
    print(f"  Skipped (err):  {skipped_error}")
    print(f"  Open positions: {len(open_pos)}")
    print(f"  Balance:        ${store.paper_balance_cents / 100:.2f}")

    # Write status file
    _write_status({
        "command": "auto",
        "timestamp": datetime.utcnow().isoformat(),
        "mode": "live" if args.live else "paper",
        "balance_cents": store.paper_balance_cents if not args.live else _get_balance(True),
        "edges_found": edges_found,
        "trades_placed": len(trades),
        "trades_skipped_existing": skipped_existing,
        "trades_skipped_error": skipped_error,
        "trades": trades,
        "open_positions": len(open_pos),
        "total_pnl_cents": store.paper_pnl_cents if not args.live else 0,
    })

    if args.json:
        _print(trades, as_json=True)


def cmd_settle(args: argparse.Namespace) -> None:
    """Settle a paper position (mark as won or lost)."""
    if args.live:
        print("Settle is only for paper trading. Live positions settle via Kalshi.", file=sys.stderr)
        sys.exit(1)

    ticker = args.ticker
    outcome = args.outcome.lower()
    won = outcome in ("w", "won", "win", "yes", "y")

    store = PositionStore.load()
    pos = store.paper_settle(ticker, won)
    if not pos:
        print(f"No open paper position for {ticker}", file=sys.stderr)
        sys.exit(1)

    result = "WON" if won else "LOST"
    payout = pos.contracts * 100 if won else 0
    cost = pos.contracts * pos.avg_price_cents
    pnl = payout - cost

    print(f"\n[PAPER] Settled {ticker}: {result}")
    print(f"  Contracts: {pos.contracts} @ {pos.avg_price_cents}¢")
    print(f"  Payout: ${payout/100:.2f}  |  Cost: ${cost/100:.2f}  |  P&L: ${pnl/100:+.2f}")
    print(f"  Balance: ${store.paper_balance_cents/100:.2f}")


def cmd_history(args: argparse.Namespace) -> None:
    """Show trade history."""
    print(_banner(args.live))

    if not args.live:
        store = PositionStore.load()
        closed = [p for p in store.closed_positions() if p.mode == "paper"]

        if args.json:
            _print([_pos_dict(p) for p in closed], as_json=True)
            return

        if not closed:
            print("\nNo paper trade history.")
            return

        print(f"\n{'Date':<12} {'Ticker':<30} {'Side':<5} {'Qty':>5} {'In':>5} {'Out':>5} {'P&L':>8}")
        print("-" * 74)
        for p in closed:
            pnl = p.pnl_cents or 0
            print(f"{p.opened_at[:10]:<12} {p.ticker:<30} {p.side:<5} {p.contracts:>5} {p.avg_price_cents:>4}¢ {p.close_price_cents or 0:>4}¢ ${pnl/100:>+7.2f}")

        print(f"\nTotal realized P&L: ${store.realized_pnl_cents/100:+.2f}")
        return

    client = _get_client()
    resp = client.get_fills()
    fills = resp.get("fills", [])

    if args.json:
        _print(fills, as_json=True)
        return

    if not fills:
        print("\nNo recent trades.")
        return

    print(f"\n{'Time':<22} {'Ticker':<30} {'Side':<5} {'Action':<5} {'Qty':>5} {'Price':>6}")
    print("-" * 75)
    for f in fills:
        ts = f.get("created_time", "")[:19]
        ticker = f.get("ticker", "")
        side = f.get("side", "")
        action = f.get("action", "")
        count = f.get("count", 0)
        price = f.get("yes_price", f.get("no_price", 0))
        print(f"{ts:<22} {ticker:<30} {side:<5} {action:<5} {count:>5} {price:>5}¢")


def cmd_reset(args: argparse.Namespace) -> None:
    """Reset paper trading account."""
    if args.live:
        print("Cannot reset live account.", file=sys.stderr)
        sys.exit(1)

    store = PositionStore()  # Fresh store with default $1000
    store.save()
    print("[PAPER] Account reset to $1,000.00")


# --- Helpers ---


_MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_event_date(event_ticker: str) -> date | None:
    """Parse date from event_ticker like 'KXHIGHNY-26FEB24' → date(2026, 2, 24)."""
    parts = event_ticker.split("-")
    if len(parts) < 2:
        return None
    date_part = parts[-1]  # e.g. "26FEB24"
    # Find month abbreviation
    for abbr, month_num in _MONTH_MAP.items():
        idx = date_part.find(abbr)
        if idx >= 0:
            try:
                year_str = date_part[:idx]          # "26" → year prefix
                day_str = date_part[idx + len(abbr):]  # "24" → day
                year = 2000 + int(year_str)
                day = int(day_str)
                return date(year, month_num, day)
            except (ValueError, IndexError):
                continue
    return None


def _markets_to_prices(markets: list[dict], target_date: date | None = None) -> dict[str, dict]:
    """Convert market list to {ticker: {strike_type, floor_strike, cap_strike, yes_price, no_price}}.

    Uses API fields (strike_type, floor_strike, cap_strike) instead of ticker parsing.
    Optionally filters to markets matching target_date via event_ticker.
    """
    prices = {}
    for m in markets:
        ticker = m.get("ticker", "")
        event_ticker = m.get("event_ticker", "")

        # Date filter: skip markets that don't match target_date
        if target_date is not None and event_ticker:
            market_date = _parse_event_date(event_ticker)
            if market_date is not None and market_date != target_date:
                continue

        strike_type = m.get("strike_type")
        if not strike_type:
            continue  # skip markets without strike_type info

        floor_strike = m.get("floor_strike")
        cap_strike = m.get("cap_strike")

        yes_price = m.get("yes_ask", m.get("last_price", 50))
        prices[ticker] = {
            "strike_type": strike_type,
            "floor_strike": floor_strike,
            "cap_strike": cap_strike,
            "yes_price": yes_price,
            "no_price": m.get("no_ask", 100 - yes_price),
        }
    return prices


def _get_balance(live: bool) -> int:
    """Get balance in cents for edge sizing."""
    if not live:
        store = PositionStore.load()
        return store.paper_balance_cents
    try:
        client = _get_client()
        return client.get_balance().get("balance", 10000)
    except Exception:
        return 10000


def _print_edges(edges: list[EdgeOpportunity], as_json: bool) -> None:
    if edges:
        print(f"\n--- EDGES DETECTED ---")
        print(f"{'Ticker':<35} {'Side':<5} {'Ens%':>6} {'Mkt¢':>6} {'Edge%':>7} {'Ctrs':>5}")
        print("-" * 66)
        for e in edges:
            print(f"{e.ticker:<35} {e.side:<5} {e.ensemble_prob:>5.1%} {e.market_price:>5.0f}¢ {e.edge_pct:>+6.1f}% {e.suggested_contracts:>5}")
    else:
        print("\nNo edges >= 8% detected.")

    if as_json:
        _print([vars(e) for e in edges], as_json=True)


def _write_status(data: dict) -> None:
    """Write machine-readable JSON status file for cron monitoring."""
    status_dir = Path.home() / ".openclaw" / "kalshi-weather"
    status_dir.mkdir(parents=True, exist_ok=True)
    status_file = status_dir / "last-run.json"
    status_file.write_text(json.dumps(data, indent=2, default=str))
    print(f"\nStatus written to {status_file}")


def _pos_dict(p) -> dict:
    """Position to serializable dict."""
    return {
        "ticker": p.ticker, "side": p.side, "contracts": p.contracts,
        "avg_price_cents": p.avg_price_cents, "opened_at": p.opened_at,
        "closed_at": p.closed_at, "close_price_cents": p.close_price_cents,
        "mode": p.mode, "pnl_cents": p.pnl_cents,
    }


# --- Main ---


def main():
    parser = argparse.ArgumentParser(
        description="Kalshi weather prediction market trading (paper mode by default)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--live", action="store_true", help="Use live/demo Kalshi API (default: paper trading)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # markets
    subparsers.add_parser("markets", help="List available weather markets")

    # market
    p_market = subparsers.add_parser("market", help="Market detail + orderbook")
    p_market.add_argument("ticker", help="Market ticker")

    # balance
    subparsers.add_parser("balance", help="Portfolio balance")

    # positions
    subparsers.add_parser("positions", help="Current positions + P&L")

    # edge
    p_edge = subparsers.add_parser("edge", help="GFS ensemble edge detection")
    p_edge.add_argument("city", help=f"City code: {', '.join(CITIES.keys())}")

    # scan
    subparsers.add_parser("scan", help="Scan all cities for edges")

    # auto
    subparsers.add_parser("auto", help="Scan all cities and auto-buy edges")

    # buy
    p_buy = subparsers.add_parser("buy", help="Place buy order")
    p_buy.add_argument("ticker", help="Market ticker")
    p_buy.add_argument("side", help="yes or no")
    p_buy.add_argument("amount", help="Dollar amount")
    p_buy.add_argument("--price", type=int, help="Price in cents (auto-fetched if omitted)")

    # sell
    p_sell = subparsers.add_parser("sell", help="Sell/close position")
    p_sell.add_argument("ticker", help="Market ticker")
    p_sell.add_argument("side", help="yes or no")
    p_sell.add_argument("amount", nargs="?", help="Dollar amount (live only)")
    p_sell.add_argument("--price", type=int, help="Price in cents (auto-fetched if omitted)")

    # auto-settle
    subparsers.add_parser("auto-settle", help="Auto-settle paper positions via Kalshi API")

    # settle
    p_settle = subparsers.add_parser("settle", help="Settle paper position (won/lost)")
    p_settle.add_argument("ticker", help="Market ticker")
    p_settle.add_argument("outcome", help="w/won/win or l/lost/lose")

    # history
    subparsers.add_parser("history", help="Trade history")

    # reset
    subparsers.add_parser("reset", help="Reset paper trading to $1000")

    args = parser.parse_args()

    commands = {
        "markets": cmd_markets,
        "market": cmd_market,
        "balance": cmd_balance,
        "positions": cmd_positions,
        "edge": cmd_edge,
        "scan": cmd_scan,
        "auto": cmd_auto,
        "buy": cmd_buy,
        "sell": cmd_sell,
        "auto-settle": cmd_auto_settle,
        "settle": cmd_settle,
        "history": cmd_history,
        "reset": cmd_reset,
    }

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
