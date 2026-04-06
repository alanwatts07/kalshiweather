import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent dir to path so we can import lib/
sys.path.insert(0, str(Path("/home/morpheus/Hackstuff/kalshiweather").resolve()))

from lib.client import KalshiClient
from lib.positions import PositionStore

def main():
    print("=== Kalshi Weather Settlement Audit ===")
    
    try:
        client = KalshiClient.from_env()
        store = PositionStore.load()
    except Exception as e:
        print(f"Error initializing: {e}")
        sys.exit(1)

    closed_positions = [p for p in store.positions if p.closed_at and p.mode == "paper"]
    
    if not closed_positions:
        print("No closed paper positions found to audit.")
        return

    print(f"Auditing {len(closed_positions)} closed paper positions...")
    print()
    
    discrepancies = []
    verified_count = 0
    not_found_count = 0
    
    print(f"{'Ticker':<35} {'Side':<5} {'Bot Res':>7} {'Kalshi':>7} {'Status':<10}")
    print("-" * 75)
    
    for pos in closed_positions:
        try:
            resp = client.get_market(pos.ticker)
            market = resp.get('market', resp)
            
            status = market.get('status', 'unknown')
            result = market.get('result', '')
            
            # If it's a paper SELL (closed manually before settlement)
            is_manual_sell = pos.close_price_cents not in (0, 100)
            
            if is_manual_sell:
                print(f"{pos.ticker:<35} {pos.side:<5} {pos.close_price_cents:>6}¢  {'N/A':>7} MANUAL SELL")
                verified_count += 1
                continue

            if status not in ('determined', 'finalized'):
                print(f"{pos.ticker:<35} {pos.side:<5} {pos.close_price_cents:>6}¢  {'?':>7} {status.upper()}")
                continue
            
            actual_won = pos.side.lower() == result.lower()
            expected_close_price = 100 if actual_won else 0
            
            match = (pos.close_price_cents == expected_close_price)
            
            res_str = f"{expected_close_price:>6}¢"
            bot_str = f"{pos.close_price_cents:>6}¢"
            
            if match:
                print(f"{pos.ticker:<35} {pos.side:<5} {bot_str}  {res_str} OK")
                verified_count += 1
            else:
                print(f"{pos.ticker:<35} {pos.side:<5} {bot_str}  {res_str} DISCREPANCY")
                discrepancies.append({
                    'ticker': pos.ticker,
                    'side': pos.side,
                    'bot_price': pos.close_price_cents,
                    'actual_result': result,
                    'expected_price': expected_close_price
                })
                
        except Exception as e:
            if '404' in str(e):
                print(f"{pos.ticker:<35} {pos.side:<5} {'?':>7}  {'?':>7} NOT FOUND")
                not_found_count += 1
            else:
                print(f"{pos.ticker:<35} {pos.side:<5} ERROR: {e}")

    print()
    print("="*30)
    print(f"Audit Summary:")
    print(f"  Verified/OK:  {verified_count}")
    print(f"  Discrepancies: {len(discrepancies)}")
    print(f"  Not Found:    {not_found_count}")
    print(f"  Total Audited: {len(closed_positions)}")
    
    if discrepancies:
        print()
        print("Discrepancy Details:")
        for d in discrepancies:
            print(f"  - {d['ticker']} ({d['side']}): Bot said {d['bot_price']}c, but Kalshi result was '{d['actual_result']}' (expected {d['expected_price']}c)")
    else:
        print()
        print("All settled trades match Kalshi records perfectly.")

if __name__ == '__main__':
    main()
