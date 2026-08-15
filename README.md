# MT5 Gold Trading Bot — BOS + Retest

Python trading bot for MetaTrader 5, currently designed around XAUUSD-style gold symbols.

## Primary strategy

The current version uses **M5 Market Structure Break (BOS) + Retest** as the primary entry/reversal signal.

- A BUY requires a confirmed swing high to be broken, followed by a retest that holds above the broken level.
- A SELL requires a confirmed swing low to be broken, followed by a retest that holds below the broken level.
- M15 and M30 are used as context/display information and do not veto a confirmed M5 BOS+retest signal.
- Opposite BOS+retest is used as the structural reversal trigger.

## Risk / basket management

The supplied configuration includes:

- Initial batch entries
- Profit-based pyramiding
- Maximum open trades
- Basket take-profit
- Hard basket loss
- Partial profit protection
- Spread filter
- Trading-session filter
- Manual news blackout windows

## Developer review requested

This repository is intended for technical review. Please investigate:

1. Why the bot can still behave incorrectly during changing market direction.
2. Whether the BOS/retest detection is robust and free from look-ahead or stale-signal problems.
3. Whether state handling after a reversal, TP, SL, or partial close can become inconsistent.
4. Whether profit pyramiding can add positions at the wrong time.
5. Whether the basket risk model is appropriate for XAUUSD.
6. Whether MT5 order execution/filling handling is robust across Exness account types.
7. Whether any legacy indicator/scoring code can be safely removed or should be integrated.
8. Whether the strategy has logical conflicts that could explain poor live/demo behaviour.

## Important

Do not commit real broker credentials, API keys, tokens, or `.env` files.

This project is for code review and development. Trading results are not guaranteed.
