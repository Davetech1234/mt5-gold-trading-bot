import MetaTrader5 as mt5
import time
import os
import getpass
import numpy as np
from datetime import datetime, timezone, timedelta


MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "Exness-MT5Trial9")

SYMBOL        = "XAUUSDm"
TIMEFRAME     = mt5.TIMEFRAME_M5
HTF_TIMEFRAME_1 = mt5.TIMEFRAME_M15  # trend confirmation
HTF_TIMEFRAME_2 = mt5.TIMEFRAME_M30   # major trend filter
# Controlled pyramid sizing. The bot NEVER increases size after a losing trade.
LOT_SEQUENCE  = [0.01, 0.01, 0.02, 0.02, 0.03, 0.03, 0.04, 0.04]
MAX_LOT       = 0.04
MAX_TRADES    = 10
INITIAL_ENTRY_TRADES = 3   # video-style initial same-direction batch
ADD_BATCH_SIZE = 2          # add a small burst at profit milestones while structure remains healthy
CHECK_EVERY   = 5      # main loop tick (seconds)
MAGIC         = 234567

# ---------------------------------------------------------------------------
# PRIMARY SIGNAL: MARKET STRUCTURE BREAK + RETEST
# ---------------------------------------------------------------------------
# The old EMA/RSI/MACD score is no longer the boss of direction.
# M5 price structure can switch direction before slow M15/M30 averages catch up.
BOS_TIMEFRAME = mt5.TIMEFRAME_M5
BOS_PIVOT_ORDER = 2
BOS_LOOKBACK = 120
BOS_MAX_RETEST_BARS = 12
BOS_MAX_SIGNAL_AGE_BARS = 3   # do not trade stale structure signals
BOS_RETEST_BUFFER_ATR = 0.25
BOS_MIN_BREAK_ATR = 0.10
BOS_REQUIRE_CLOSE_BEYOND = True
BOS_SIGNAL_COOLDOWN_SECONDS = 30

# M15/M30 are context only. They NEVER veto a confirmed M5 BOS+retest signal.
USE_M15_CONTEXT = True
USE_M30_CONTEXT = True

# Reversal is now structural: opposite BOS+retest closes the current basket.
REVERSAL_CONFIRMATION = "M5_BOS_RETEST"

# --- Basket TP / hard SL ---
# New strategy: let a strong trend run toward the full basket TP.
# A strong M5 reversal closes the entire basket to protect the profit.
BASKET_TP = 40.0          # final basket target
PROFIT_ADD_STEP = 2.0     # add after each profit milestone while trend remains healthy
MAX_BASKET_SL = 25.0      # hard basket loss
PARTIAL_PROFIT_TRIGGER = 20.0  # protect half the basket at 50% of TP
PARTIAL_CLOSE_FRACTION = 0.50
REVERSAL_COOLDOWN_SECONDS = 3  # prevents duplicate entries during a direction flip

# Profit is protected by the strong-reversal exit, not by a separate
# percentage trailing stop. Strong trend = keep adding/running;
# strong reversal = close everything.

# --- ATR used for volatility / hard SL / trailing calculations ---
ATR_PERIOD          = 14
# Profit-based pyramiding replaces ATR-distance grid spacing.
# The bot adds only after the basket reaches the next $2 milestone and
# only while the trend remains strong.

# --- ATR-based trailing stop ---
# Trailing distance (in $) = ATR (price units) * multiplier * total open
# volume * contract size — this converts the price-based ATR into a
# dollar amount that matches how much the basket's floating P/L actually
# moves per $1 of price change, instead of a flat, volatility-blind $3.
#
# PROFIT PROTECTION: the raw ATR distance is then capped at
# MAX_GIVEBACK_FRACTION of the peak profit, so the bot can never give
# back more than that share of the best profit it saw — e.g. at a $8.90
# peak with a 25% cap, it locks in at least $6.68, not $1.96.
ATR_TRAIL_MULTIPLIER   = 1.5
TRAIL_DISTANCE_MIN     = 1.0    # floor so trailing stop isn't ~0 in a dead market
MAX_GIVEBACK_FRACTION  = 0.25   # never give back more than 25% of peak profit

# --- Spread filter ---
# Skip new entries/grid adds if the current spread is too wide (e.g.
# around rollover or thin liquidity) — a wide spread eats into any edge
# the strategy has before the trade even starts moving.
MAX_SPREAD = 0.35

# --- Trading-session filter (UTC) ---
# Only take NEW entries/grid adds during London+New York hours, when
# gold liquidity is best and spreads are tightest. Existing positions
# are still managed (TP/SL/reversal/trailing) outside this window —
# only new trades are blocked.
SESSION_START_HOUR = 7    # 07:00 UTC ~ London open
SESSION_END_HOUR   = 20   # 20:00 UTC ~ New York close

# --- Smarter entries ---
# Beyond basic EMA/RSI/ADX agreement, an entry must also show growing
# momentum (MACD histogram moving further in the trade's direction, not
# just aligned), acceptable volatility (ATR inside a sane band — too low
# means a dead market not worth the spread, too high often means a spike
# that's about to mean-revert), and price not already over-extended away
# from EMA9 (chasing a candle that already ran far tends to buy the top
# / sell the bottom of a move).
ATR_MIN = 0.15    # below this, market is too quiet to bother trading
ATR_MAX = 15.5     # above this, likely a news-spike / low-quality entry
MAX_EXTENSION_ATR = 2.0  # price vs EMA9 distance, in multiples of ATR

# --- Grid management ---
# Only add another grid level if the basket is still healthy — trend
# still strong (ADX) and momentum still aligned (MACD) — instead of
# blindly averaging into a fading or reversing move.
MIN_HEALTHY_ADX = 20

# --- Candlestick confirmation ---
# The last CLOSED candle must show an engulfing pattern or a rejection
# wick (pin bar / hammer / shooting star) in the trade's direction —
# proof buyers/sellers actually showed up, not just that indicators
# crossed.
PIN_WICK_BODY_RATIO = 2.0  # wick must be at least this many times the candle body

# --- Support/resistance ---
# Recent swing highs/lows (fractal pivots) over a lookback window.
# Blocks buying straight into overhead resistance or selling straight
# into support below — the two most common ways a technically "valid"
# trend-following entry immediately fails.
SR_LOOKBACK        = 100   # bars to scan for swing points
SR_PIVOT_ORDER     = 3     # bars on each side that must be lower/higher to count as a pivot
SR_BUFFER_ATR_MULT = 1.0   # how close (in ATR) counts as "into" a level

# --- Trend strength scoring ---
# Replaces the old flat "score >= 3 of 5" entry gate with a composite
# 0-10 score: base trend agreement (0-5) + ADX strength bonus (0-2) +
# momentum-growing bonus (0-1) + candle confirmation (0-1) + clear of
# S/R (0-1). Only the strongest setups (MIN_SETUP_SCORE or higher)
# are traded — this is the main lever for "fewer, better" trades.
MIN_SETUP_SCORE = 4   # out of 9 for the M5 entry trigger
M15_DIRECTION_SCORE_MIN = 4  # 4/7 = directional trend, not an entry gate
M5_ENTRY_SCORE_MIN = 4       # M5 timing trigger after M15+M30 agree (out of 9)
ADX_STRONG      = 30
ADX_DECENT      = 25

# --- News filter ---
# No live economic-calendar feed is connected, so this is a manually
# maintained blackout list rather than an auto-fetched one. Add windows
# yourself from a calendar site (e.g. ForexFactory) in UTC, format
# "YYYY-MM-DD HH:MM". The bot will not open new trades / add grid
# levels during these windows (existing positions are NOT force-closed —
# TP/SL/reversal/trailing logic still applies to them as normal).
NEWS_BLACKOUT_WINDOWS = [
    ("2026-08-07 12:25", "2026-08-07 13:00"),  # NFP (July jobs report)
    ("2026-08-12 12:25", "2026-08-12 13:00"),  # CPI (July inflation)
    ("2026-09-16 17:55", "2026-09-16 19:30"),  # FOMC decision + press conference
]
POST_NEWS_BUFFER_MINUTES = 15  # stay out this much longer after each window ends too

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect():
    global MT5_LOGIN, MT5_PASSWORD
    if MT5_LOGIN == 0:
        try:
            MT5_LOGIN = int(input("MT5 login: ").strip())
        except ValueError:
            print("Invalid MT5 login.")
            return False
    if not MT5_PASSWORD:
        MT5_PASSWORD = getpass.getpass("MT5 password: ")
    print("Connecting to MT5...")
    if not mt5.initialize():
        print(f"Failed: {mt5.last_error()}")
        return False
    if mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        info = mt5.account_info()
        print(f"Connected! Account: {info.login} | Balance: ${info.balance:.2f}")
        return True
    print(f"Login failed: {mt5.last_error()}")
    return False

def resolve_symbol():
    """
    Make sure SYMBOL actually exists and is visible in Market Watch on
    THIS account, and auto-correct it if not. Gold's suffix (m/c/none/etc.)
    varies by broker account type, so a symbol that worked on one account
    (e.g. a demo) may not exist under the same name on another (e.g. a
    real/cent account) — this is what caused "Failed to select XAUUSDm".
    """
    global SYMBOL

    info = mt5.symbol_info(SYMBOL)
    if info is not None:
        if not info.visible and not mt5.symbol_select(SYMBOL, True):
            print(f"  ❌ Found '{SYMBOL}' but couldn't add it to Market Watch: {mt5.last_error()}")
            return False
        print(f"  ✅ Using symbol '{SYMBOL}'")
        return True

    # SYMBOL as configured doesn't exist on this account — search for
    # any gold symbol actually available and use that instead.
    print(f"  ⚠️ '{SYMBOL}' not found on this account. Searching for gold symbols...")
    all_symbols = mt5.symbols_get()
    if all_symbols is None:
        print(f"  ❌ Could not list symbols: {mt5.last_error()}")
        return False

    candidates = [s.name for s in all_symbols if "XAU" in s.name.upper()]
    if not candidates:
        print("  ❌ No gold (XAU) symbols found on this account at all.")
        print("     Check the Market Watch panel in MT5 for the exact gold symbol name.")
        return False

    print(f"  ℹ️ Available gold symbols on this account: {candidates}")
    SYMBOL = candidates[0]
    if not mt5.symbol_select(SYMBOL, True):
        print(f"  ❌ Found '{SYMBOL}' but couldn't select it: {mt5.last_error()}")
        return False

    print(f"  ✅ Auto-switched to '{SYMBOL}'")
    return True

# ---------------------------------------------------------------------------
# Indicators
# ---------------------------------------------------------------------------

def calculate_rsi(closes, period=14):
    closes = np.array(closes)
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_ema(closes, period):
    closes = np.array(closes, dtype=float)
    k = 2 / (period + 1)
    ema = closes[0]
    for p in closes[1:]:
        ema = p * k + ema * (1 - k)
    return ema

def calculate_atr(rates, period=14):
    highs  = np.array([r['high']  for r in rates], dtype=float)
    lows   = np.array([r['low']   for r in rates], dtype=float)
    closes = np.array([r['close'] for r in rates], dtype=float)

    prev_close = closes[:-1]
    tr = np.maximum(highs[1:] - lows[1:],
         np.maximum(np.abs(highs[1:] - prev_close), np.abs(lows[1:] - prev_close)))

    def wilder_smooth(values, period):
        smoothed = [np.sum(values[:period])]
        for v in values[period:]:
            smoothed.append(smoothed[-1] - (smoothed[-1] / period) + v)
        return np.array(smoothed)

    atr = wilder_smooth(tr, period) / period
    return atr[-1]

def calculate_adx(rates, period=14):
    highs  = np.array([r['high']  for r in rates], dtype=float)
    lows   = np.array([r['low']   for r in rates], dtype=float)
    closes = np.array([r['close'] for r in rates], dtype=float)

    up_move   = highs[1:] - highs[:-1]
    down_move = lows[:-1] - lows[1:]

    plus_dm  = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    prev_close = closes[:-1]
    tr = np.maximum(highs[1:] - lows[1:],
         np.maximum(np.abs(highs[1:] - prev_close), np.abs(lows[1:] - prev_close)))

    def wilder_smooth(values, period):
        smoothed = [np.sum(values[:period])]
        for v in values[period:]:
            smoothed.append(smoothed[-1] - (smoothed[-1] / period) + v)
        return np.array(smoothed)

    atr      = wilder_smooth(tr, period)
    plus_di  = 100 * wilder_smooth(plus_dm, period) / atr
    minus_di = 100 * wilder_smooth(minus_dm, period) / atr

    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = np.mean(dx[-period:])
    return round(adx, 2)

# ---------------------------------------------------------------------------
# Market state — computed ONCE per loop tick and reused everywhere.
# This replaces the old get_trend() / is_reversal() pair that each pulled
# 250 bars and recomputed every EMA from scratch, sometimes twice per tick.
# ---------------------------------------------------------------------------

def compute_support_resistance(rates, lookback=SR_LOOKBACK, order=SR_PIVOT_ORDER):
    """Simple fractal pivot detection: a bar is a swing high/low if its
    high/low is the most extreme within `order` bars on each side."""
    highs = np.array([r['high'] for r in rates], dtype=float)[-lookback:]
    lows  = np.array([r['low']  for r in rates], dtype=float)[-lookback:]

    resistances, supports = [], []
    for i in range(order, len(highs) - order):
        window_h = highs[i - order:i + order + 1]
        if highs[i] == window_h.max():
            resistances.append(highs[i])
        window_l = lows[i - order:i + order + 1]
        if lows[i] == window_l.min():
            supports.append(lows[i])
    return resistances, supports

def near_resistance(price, resistances, buffer):
    return any(0 <= r - price <= buffer for r in resistances)

def near_support(price, supports, buffer):
    return any(0 <= price - s <= buffer for s in supports)

def get_candle_signal(state, direction):
    """True if the last CLOSED candle shows an engulfing pattern or a
    rejection wick (pin bar) in the given direction."""
    candles = state["candles"]
    if len(candles) < 2:
        return False
    prev, curr = candles[-2], candles[-1]

    body  = abs(curr["close"] - curr["open"])
    rng   = curr["high"] - curr["low"]
    upper_wick = curr["high"] - max(curr["open"], curr["close"])
    lower_wick = min(curr["open"], curr["close"]) - curr["low"]
    if rng <= 0:
        return False

    if direction == "BUY":
        bullish_engulfing = (curr["close"] > curr["open"] and prev["close"] < prev["open"]
                              and curr["close"] >= prev["open"] and curr["open"] <= prev["close"])
        hammer_rejection = (lower_wick >= body * PIN_WICK_BODY_RATIO and lower_wick > upper_wick)
        return bullish_engulfing or hammer_rejection

    if direction == "SELL":
        bearish_engulfing = (curr["close"] < curr["open"] and prev["close"] > prev["open"]
                              and curr["close"] <= prev["open"] and curr["open"] >= prev["close"])
        shooting_star = (upper_wick >= body * PIN_WICK_BODY_RATIO and upper_wick > lower_wick)
        return bearish_engulfing or shooting_star

    return False

def get_market_state(timeframe=TIMEFRAME):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, 250)
    if rates is None or len(rates) < 200:
        return None

    closes = [r['close'] for r in rates]
    resistances, supports = compute_support_resistance(rates)

    # Last 2 CLOSED candles (rates[-1] is the still-forming current bar).
    candles = [
        {"open": r['open'], "high": r['high'], "low": r['low'], "close": r['close']}
        for r in rates[-4:-1]
    ]

    state = {
        "rsi":            calculate_rsi(closes),
        "ema9":           calculate_ema(closes, 9),
        "ema21":          calculate_ema(closes, 21),
        "ema50":          calculate_ema(closes, 50),
        "ema200":         calculate_ema(closes, 200),
        "last_close":     closes[-1],
        "prev_close":     closes[-2],
        "adx":            calculate_adx(rates),
        "atr":            calculate_atr(rates, ATR_PERIOD),
        "resistances":    resistances,
        "supports":       supports,
        "candles":        candles,
    }
    state["info"] = (
        f"RSI={state['rsi']:.1f} | "
        f"EMA9={state['ema9']:.2f} | "
        f"EMA21={state['ema21']:.2f} | "
        f"EMA50={state['ema50']:.2f} | "
        f"EMA200={state['ema200']:.2f} | "
        f"ADX={state['adx']:.1f} | "
        f"ATR={state['atr']:.2f}"
    )
    return state

def get_htf_trend(timeframe):
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, 210)
    if rates is None or len(rates) < 200:
        return None

    closes = [r['close'] for r in rates]

    ema9 = calculate_ema(closes, 9)
    ema21 = calculate_ema(closes, 21)
    ema50 = calculate_ema(closes, 50)
    ema200 = calculate_ema(closes, 200)
    price = closes[-1]

    buy_score = 0
    sell_score = 0

    if ema9 > ema21:
        buy_score += 1
    else:
        sell_score += 1

    if ema50 > ema200:
        buy_score += 1
    else:
        sell_score += 1

    if price > ema50:
        buy_score += 1
    else:
        sell_score += 1

    if buy_score >= 2:
        return "BUY"

    if sell_score >= 2:
        return "SELL"

    return None

def is_news_time():
    """True if we're currently inside a manually configured news
    blackout window (see NEWS_BLACKOUT_WINDOWS), extended by
    POST_NEWS_BUFFER_MINUTES on the back end to avoid the volatile
    aftermath of a release, not just the release itself. Blocks new
    entries and grid adds only — does not touch existing open positions."""
    if not NEWS_BLACKOUT_WINDOWS:
        return False
    now = datetime.now(timezone.utc)
    for start_str, end_str in NEWS_BLACKOUT_WINDOWS:
        start = datetime.strptime(start_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        end   = datetime.strptime(end_str,   "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        end_buffered = end + timedelta(minutes=POST_NEWS_BUFFER_MINUTES)
        if start <= now <= end_buffered:
            return True
    return False

def is_entry_quality_ok(state, direction):
    """
    Extra quality gate beyond basic trend/RSI agreement:
    - momentum growing in the trade direction
    - ATR not too low or too high
    - price not overextended from EMA9
    """

    # ATR filter
    if not (ATR_MIN <= state["atr"] <= ATR_MAX):
        print(f"✘ {direction} rejected: ATR={state['atr']:.2f} is outside {ATR_MIN}-{ATR_MAX}")
        return False

    # Distance from EMA9
    extension = abs(state["last_close"] - state["ema9"])

    if extension > state["atr"] * MAX_EXTENSION_ATR:
        print(f"✘ {direction} rejected: Price too far from EMA9")
        return False

    print(f"✅ {direction} quality check passed")
    return True

def get_setup_score(state, direction):
    """Composite 0-9 score for how strong a setup is:
    - 0-5: base trend agreement (EMA50/200, EMA9/21, RSI, last candle)
    - 0-2: ADX trend-strength bonus
    - 0-1: candlestick confirmation (engulfing / pin bar)
    - 0-1: not currently sitting right into resistance (BUY) / support (SELL)
    """
    score = 0
    if direction == "BUY":
        if state["ema50"] > state["ema200"]: score += 2
        if state["ema9"] > state["ema21"]:   score += 1
        if state["rsi"] > 50:                score += 1
        if state["last_close"] > state["prev_close"]: score += 1
    else:
        if state["ema50"] < state["ema200"]: score += 2
        if state["ema9"] < state["ema21"]:   score += 1
        if state["rsi"] < 50:                score += 1
        if state["last_close"] < state["prev_close"]: score += 1

    if state["adx"] >= ADX_STRONG:
        score += 2
    elif state["adx"] >= ADX_DECENT:
        score += 1

    if get_candle_signal(state, direction):
        score += 1

    buffer = state["atr"] * SR_BUFFER_ATR_MULT
    if direction == "BUY" and not near_resistance(state["last_close"], state["resistances"], buffer):
        score += 1
    if direction == "SELL" and not near_support(state["last_close"], state["supports"], buffer):
        score += 1

    return score

def get_direction_score(state, direction):
    """Directional trend score for M15 only.

    This deliberately answers a different question from get_setup_score():
    "Which way is the market trending?" It does NOT require the candle,
    support/resistance, momentum-growth, or entry-quality filters that can
    legitimately delay an entry.

    Maximum = 7:
      EMA50/200 structure = 2
      EMA9/21 structure   = 1
      price vs EMA50      = 1
      RSI direction       = 1
      last closed candle  = 1
      ADX strength        = 1
    """
    score = 0
    if direction == "BUY":
        if state["ema50"] > state["ema200"]: score += 2
        if state["ema9"] > state["ema21"]: score += 1
        if state["last_close"] > state["ema50"]: score += 1
        if state["rsi"] > 50: score += 1
        if state["last_close"] > state["prev_close"]: score += 1
    else:
        if state["ema50"] < state["ema200"]: score += 2
        if state["ema9"] < state["ema21"]: score += 1
        if state["last_close"] < state["ema50"]: score += 1
        if state["rsi"] < 50: score += 1
        if state["last_close"] < state["prev_close"]: score += 1

    if state["adx"] >= 20:
        score += 1
    return score


def get_m15_direction(state):
    """Return BUY/SELL/NONE based only on M15 directional structure."""
    if state is None:
        return None, 0, 0
    buy_score = get_direction_score(state, "BUY")
    sell_score = get_direction_score(state, "SELL")
    if buy_score >= M15_DIRECTION_SCORE_MIN and buy_score > sell_score:
        return "BUY", buy_score, sell_score
    if sell_score >= M15_DIRECTION_SCORE_MIN and sell_score > buy_score:
        return "SELL", buy_score, sell_score
    return None, buy_score, sell_score


def get_trend(state):
    """Backward-compatible alias for M15 directional trend."""
    direction, _, _ = get_m15_direction(state)
    return direction


def spread_ok():
    """True if the current bid/ask spread is tight enough to trade."""
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        return False
    spread = tick.ask - tick.bid
    return spread <= MAX_SPREAD

def in_trading_session():
    """True if we're currently inside the allowed trading-session hours
    (UTC). Only gates NEW entries/grid adds — existing positions are
    still managed normally outside this window."""
    hour = datetime.now(timezone.utc).hour
    if SESSION_START_HOUR <= SESSION_END_HOUR:
        return SESSION_START_HOUR <= hour < SESSION_END_HOUR
    return hour >= SESSION_START_HOUR or hour < SESSION_END_HOUR  # wraps past midnight UTC

def get_next_add_profit(trade_count):
    """Profit milestone for the next pyramid add: $2, $4, $6, $8."""
    return PROFIT_ADD_STEP * trade_count

def get_dynamic_tp_sl(state, positions):
    """Return the fixed basket TP and fixed maximum basket loss."""
    return BASKET_TP, MAX_BASKET_SL

def basket_is_healthy(state, direction, total_profit, sl):
    """Gate for adding another grid level: only add if the trend is
    still strong (ADX) and the basket is not deeply underwater.
    MACD is intentionally not used as a hard blocker."""
    if state["adx"] < MIN_HEALTHY_ADX:
        return False
    # Don't add to a basket that's already deep in drawdown — that's
    # averaging down into weakness, not adding to strength.
    if total_profit <= -sl * 0.5:
        return False
    return True

def can_add_profit_grid(total_profit, next_add_profit, current_direction, trend, state):
    """Add only when a profit milestone is reached AND ADX/trend remains healthy. MACD is disabled."""
    if current_direction != trend:
        return False
    if state["adx"] < MIN_HEALTHY_ADX:
        return False
    return total_profit >= next_add_profit


# ---------------------------------------------------------------------------
# Market Structure Break + Retest signal engine
# ---------------------------------------------------------------------------

def get_closed_rates(timeframe, count=BOS_LOOKBACK):
    """Return only CLOSED candles, newest last. The current forming candle is excluded."""
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 1, count)
    if rates is None or len(rates) < max(30, BOS_PIVOT_ORDER * 2 + 10):
        return None
    return rates


def _confirmed_swings(rates, order=BOS_PIVOT_ORDER):
    """Find confirmed fractal swing highs/lows without using future bars as live data."""
    highs = np.array([float(r['high']) for r in rates])
    lows = np.array([float(r['low']) for r in rates])
    swing_highs, swing_lows = [], []

    for i in range(order, len(rates) - order):
        h_window = highs[i-order:i+order+1]
        l_window = lows[i-order:i+order+1]
        if highs[i] == np.max(h_window) and np.sum(h_window == highs[i]) == 1:
            swing_highs.append((i, float(highs[i])))
        if lows[i] == np.min(l_window) and np.sum(l_window == lows[i]) == 1:
            swing_lows.append((i, float(lows[i])))
    return swing_highs, swing_lows


def _candle_retests_level(candle, level, direction, buffer):
    """True when the candle trades back to the broken level and closes on the new side."""
    o, h, l, c = map(float, (candle['open'], candle['high'], candle['low'], candle['close']))
    if direction == 'BUY':
        touched = l <= level + buffer
        held = c > level
        rejection = c >= o or (c - l) > (h - c)
        return touched and held and rejection
    touched = h >= level - buffer
    held = c < level
    rejection = c <= o or (h - c) > (c - l)
    return touched and held and rejection


def detect_bos_retest(timeframe=BOS_TIMEFRAME):
    """
    Detect the newest completed Market Structure Break -> Retest -> Hold.

    BUY: a confirmed swing high is closed above, then a later candle retests the
         broken high and closes back above it.
    SELL: a confirmed swing low is closed below, then a later candle retests the
          broken low and closes back below it.

    Returns a dict or None. This is intentionally price-structure-first; EMA,
    RSI, MACD and ADX do not veto the signal.
    """
    rates = get_closed_rates(timeframe)
    if rates is None:
        return None

    swings_h, swings_l = _confirmed_swings(rates)
    atr = calculate_atr(rates, ATR_PERIOD)
    if atr is None or atr <= 0:
        return None
    buffer = atr * BOS_RETEST_BUFFER_ATR
    min_break = atr * BOS_MIN_BREAK_ATR

    candidates = []

    # Search both directions. The latest completed retest wins.
    for direction, swings, price_key in (('BUY', swings_h, 'high'), ('SELL', swings_l, 'low')):
        for swing_idx, level in swings:
            # A breakout must happen after the swing and before the final retest window.
            for j in range(swing_idx + 1, len(rates) - 1):
                prev_close = float(rates[j-1]['close'])
                close = float(rates[j]['close'])
                high = float(rates[j]['high'])
                low = float(rates[j]['low'])

                if direction == 'BUY':
                    broke = close > level and prev_close <= level
                    break_strength = close - level
                else:
                    broke = close < level and prev_close >= level
                    break_strength = level - close

                if not broke or break_strength < min_break:
                    continue

                max_k = min(len(rates) - 1, j + BOS_MAX_RETEST_BARS)
                for k in range(j + 1, max_k + 1):
                    if _candle_retests_level(rates[k], level, direction, buffer):
                        # The signal belongs to the retest candle. We only use
                        # completed candles, so this cannot fire on an unfinished bar.
                        candidates.append({
                            'direction': direction,
                            'level': level,
                            'breakout_time': int(rates[j]['time']),
                            'retest_time': int(rates[k]['time']),
                            'breakout_index': j,
                            'retest_index': k,
                            'atr': float(atr),
                            'buffer': float(buffer),
                            'break_strength': float(break_strength),
                        })
                        break

    if not candidates:
        return None

    # Most recent retest is the actionable structure signal.
    signal = max(candidates, key=lambda x: x['retest_time'])

    # Never act on a stale BOS+retest. The market may have materially changed
    # after the retest, so only the most recent few CLOSED bars are actionable.
    latest_index = len(rates) - 1
    if latest_index - signal['retest_index'] > BOS_MAX_SIGNAL_AGE_BARS:
        return None
    return signal


def get_structure_signal():
    """Get the latest M5 BOS+retest and its M15/M30 context for display only."""
    signal = detect_bos_retest(BOS_TIMEFRAME)
    m15 = get_htf_trend(HTF_TIMEFRAME_1) if USE_M15_CONTEXT else None
    m30 = get_htf_trend(HTF_TIMEFRAME_2) if USE_M30_CONTEXT else None
    return signal, m15, m30


def structure_signal_is_new(signal, last_signal_key):
    if not signal:
        return False
    key = (signal['direction'], signal['breakout_time'], signal['retest_time'])
    return key != last_signal_key


def structure_signal_key(signal):
    if not signal:
        return None
    return (signal['direction'], signal['breakout_time'], signal['retest_time'])

# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def normalize_volume(volume):
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return round(volume, 2)
    step = info.volume_step or 0.01
    minimum = info.volume_min or step
    maximum = info.volume_max or volume
    volume = min(max(volume, minimum), maximum, MAX_LOT)
    steps = round(volume / step)
    return round(max(minimum, steps * step), 2)

def get_pyramid_lot(trade_count):
    index = min(trade_count, len(LOT_SEQUENCE) - 1)
    return normalize_volume(LOT_SEQUENCE[index])

def open_trade(direction, volume=None):
    tick = mt5.symbol_info_tick(SYMBOL)
    if tick is None:
        print("  ❌ No tick data — cannot open trade")
        return False

    price = tick.ask if direction == "BUY" else tick.bid
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
    volume = normalize_volume(volume if volume is not None else get_pyramid_lot(0))
    request = {
        "action"      : mt5.TRADE_ACTION_DEAL,
        "symbol"      : SYMBOL,
        "volume"      : volume,
        "type"        : order_type,
        "price"       : price,
        "deviation"   : 50,
        "magic"       : MAGIC,
        "comment"     : "GridBot",
        "type_time"   : mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)

    if result is None:
        print(f"  ❌ order_send returned None — last_error: {mt5.last_error()}")
        return False

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"  ✅ {direction} opened @ {price:.3f}")
        return True

    print(f"  ❌ Failed: {result.retcode} - {result.comment}")
    return False

def close_specific_trades(positions_to_close, reason):
    if not positions_to_close:
        return 0.0
    print(f"\n  🔔 {reason} — Closing {len(positions_to_close)} trade(s)!")
    total = 0.0
    for pos in positions_to_close:
        tick = mt5.symbol_info_tick(pos.symbol)
        if tick is None:
            continue
        if pos.type == mt5.ORDER_TYPE_BUY:
            close_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            close_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        request = {
            "action"      : mt5.TRADE_ACTION_DEAL,
            "symbol"      : pos.symbol,
            "volume"      : pos.volume,
            "type"        : close_type,
            "position"    : pos.ticket,
            "price"       : price,
            "deviation"   : 50,
            "magic"       : MAGIC,
            "comment"     : "CloseAll",
            "type_time"   : mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            emoji = "💰" if pos.profit > 0 else "🔴"
            print(f"  {emoji} Closed #{pos.ticket} | P/L: ${pos.profit:.2f}")
            total += pos.profit
        else:
            retcode = result.retcode if result is not None else "None"
            print(f"  ❌ Failed to close #{pos.ticket} — retcode: {retcode}")
    print(f"  📊 Total closed P/L: ${total:.2f}")
    return total

def close_all_trades(reason):
    positions = mt5.positions_get(magic=MAGIC)
    if not positions:
        return
    close_specific_trades(list(positions), reason)

def close_partial_trades(positions, fraction, reason):
    """Reduce each position by a fraction, respecting broker volume rules."""
    if not positions:
        return 0.0
    print(f"\n  🛡️ {reason} — Partially closing {len(positions)} trade(s)")
    total = 0.0
    for pos in positions:
        info = mt5.symbol_info(pos.symbol)
        tick = mt5.symbol_info_tick(pos.symbol)
        if info is None or tick is None:
            continue
        step = info.volume_step or 0.01
        minimum = info.volume_min or step
        close_volume = pos.volume * fraction
        close_volume = round(round(close_volume / step) * step, 2)
        if close_volume < minimum or close_volume >= pos.volume:
            continue
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": close_volume,
            "type": close_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 50,
            "magic": MAGIC,
            "comment": "PartialProtect",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            estimated = pos.profit * (close_volume / pos.volume)
            total += estimated
            print(f"  💰 Partial #{pos.ticket} | volume {close_volume:.2f} | approx P/L ${estimated:.2f}")
    return total

def get_basket_direction(positions):
    """Return one direction only. Mixed directions are treated as an unsafe state."""
    if not positions:
        return None
    types = {p.type for p in positions}
    if len(types) != 1:
        return "MIXED"
    return "BUY" if next(iter(types)) == mt5.ORDER_TYPE_BUY else "SELL"


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_status(positions, tp, sl, next_add_profit):
    info   = mt5.account_info()
    count  = len(positions)
    profit = sum(p.profit for p in positions)
    direction = positions[0].type if positions else None
    dir_str = "BUY 📈" if direction == 0 else "SELL 📉" if direction == 1 else "None"
    print(f"\n{'='*45}")
    print(f"  Balance   : ${info.balance:.2f}")
    print(f"  Equity    : ${info.equity:.2f}")
    print(f"  Direction : {dir_str}")
    print(f"  Trades    : {count}/{MAX_TRADES}")
    print(f"  Total P/L : ${profit:.2f}")
    print(f"  TP: ${tp:.2f} | SL: ${sl:.2f} | Next add: ${next_add_profit:.2f}")
    print(f"{'='*45}\n")

# ---------------------------------------------------------------------------
# Main loop — BOS + Retest primary engine
# ---------------------------------------------------------------------------

def reset_basket_state():
    return None, 0.0, False, None, None, 0, PROFIT_ADD_STEP


def run():
    print("="*55)
    print("  GOLD BOT V10 | XAUUSDm | BOS + RETEST")
    print("  PRIMARY: M5 Market Structure Break -> Retest -> Hold")
    print("  M15/M30: CONTEXT ONLY — NEVER VETO A VALID M5 STRUCTURE SIGNAL")
    print(f"  Initial batch: {INITIAL_ENTRY_TRADES} | Add burst: {ADD_BATCH_SIZE} | Max: {MAX_TRADES}")
    print(f"  TP: ${BASKET_TP:.2f} | Hard basket SL: ${MAX_BASKET_SL:.2f} | Partial: ${PARTIAL_PROFIT_TRIGGER:.2f}")
    print("  REVERSAL: opposite M5 BOS+RETEST -> CLOSE ALL -> WAIT -> fresh signal")
    print("  MACD: NOT USED AS A TRADE BLOCKER")
    print("  CTRL+C to stop")
    print("="*55)

    if not connect():
        input("Press Enter to exit...")
        return
    if not resolve_symbol():
        input("Press Enter to exit...")
        return

    current_direction = None
    peak_profit = 0.0
    partial_taken = False
    reversal_wait = False
    reversal_origin = None
    basket_tp = None
    basket_sl = None
    prev_position_count = 0
    next_add_profit = PROFIT_ADD_STEP
    last_consumed_signal_key = None
    last_reversal_time = 0.0
    scan = 0

    try:
        while True:
            positions = list(mt5.positions_get(magic=MAGIC) or [])
            actual_direction = get_basket_direction(positions)

            if actual_direction == "MIXED":
                print("  🚨 MIXED BUY/SELL state — closing all for one-direction safety")
                close_all_trades("Safety: mixed-direction basket")
                positions = []
                current_direction = None
            elif actual_direction:
                current_direction = actual_direction

            # ---------------------------------------------------------------
            # Read structure signal first. This is the PRIMARY decision.
            # ---------------------------------------------------------------
            signal, m15_context, m30_context = get_structure_signal()
            signal_key = structure_signal_key(signal)
            news_blackout = is_news_time()

            if signal:
                signal_text = (
                    f"{signal['direction']} | level={signal['level']:.2f} | "
                    f"break={datetime.fromtimestamp(signal['breakout_time']).strftime('%H:%M:%S')} | "
                    f"retest={datetime.fromtimestamp(signal['retest_time']).strftime('%H:%M:%S')} | "
                    f"ATR={signal['atr']:.2f}"
                )
            else:
                signal_text = "NONE"

            if positions:
                total_profit = sum(p.profit for p in positions)
                peak_profit = max(peak_profit, total_profit)

                if basket_tp is None or len(positions) != prev_position_count:
                    basket_tp, basket_sl = get_dynamic_tp_sl(None, positions)
                    prev_position_count = len(positions)
                tp, sl = basket_tp, basket_sl

                # 1) Hard basket SL.
                if total_profit <= -sl:
                    close_all_trades(f"🔴 HARD BASKET SL HIT! ${total_profit:.2f}")
                    current_direction, peak_profit, partial_taken, basket_tp, basket_sl, prev_position_count, next_add_profit = reset_basket_state()
                    reversal_wait = False
                    reversal_origin = None

                # 2) Partial protection.
                elif (not partial_taken) and total_profit >= PARTIAL_PROFIT_TRIGGER:
                    close_partial_trades(
                        positions, PARTIAL_CLOSE_FRACTION,
                        f"🛡️ PARTIAL PROFIT at ${total_profit:.2f}"
                    )
                    partial_taken = True

                # 3) Full basket TP.
                elif total_profit >= tp:
                    close_all_trades(f"💰 BASKET TP HIT! ${total_profit:.2f}")
                    current_direction, peak_profit, partial_taken, basket_tp, basket_sl, prev_position_count, next_add_profit = reset_basket_state()
                    reversal_wait = False
                    reversal_origin = None

                # 4) STRUCTURAL REVERSAL: opposite BOS + retest.
                elif signal and signal['direction'] != current_direction:
                    new_signal = structure_signal_is_new(signal, last_consumed_signal_key)
                    cooldown_ok = time.time() >= last_reversal_time + BOS_SIGNAL_COOLDOWN_SECONDS
                    if new_signal and cooldown_ok:
                        print(
                            f"\n  🔄 STRUCTURAL REVERSAL: {current_direction} -> {signal['direction']}"
                        )
                        print(
                            f"  🔥 BOS+RETEST confirmed | broken level={signal['level']:.2f} | "
                            f"retest={datetime.fromtimestamp(signal['retest_time']).strftime('%H:%M:%S')}"
                        )
                        reversal_origin = current_direction
                        reversal_wait = True
                        last_consumed_signal_key = signal_key
                        last_reversal_time = time.time()
                        close_all_trades(
                            f"🔄 BOS+RETEST REVERSAL {current_direction}->{signal['direction']} — CLOSE + WAIT"
                        )
                        current_direction = None
                        peak_profit = 0.0
                        partial_taken = False
                        basket_tp = None
                        basket_sl = None
                        prev_position_count = 0
                        next_add_profit = PROFIT_ADD_STEP
                        positions = []

                # 5) Profit pyramiding in the SAME structural direction.
                elif len(positions) < MAX_TRADES:
                    if news_blackout:
                        print("  📰 News blackout — skipping pyramid add")
                    elif not in_trading_session():
                        print("  🌙 Outside trading session — skipping pyramid add")
                    elif not spread_ok():
                        print("  📏 Spread too wide — skipping pyramid add")
                    elif current_direction != (signal['direction'] if signal else current_direction):
                        print("  ⏸️ No fresh same-direction structure confirmation — no add")
                    elif total_profit < next_add_profit:
                        print(f"  ⏳ Waiting for next profit milestone ${next_add_profit:.2f} | current ${total_profit:.2f}")
                    else:
                        room = MAX_TRADES - len(positions)
                        burst = min(ADD_BATCH_SIZE, room)
                        print(f"  📈 PROFIT MILESTONE ${next_add_profit:.2f} — adding {burst} {current_direction} position(s)")
                        opened_now = 0
                        for j in range(burst):
                            lot = get_pyramid_lot(len(positions) + j)
                            if open_trade(current_direction, lot):
                                opened_now += 1
                                print(f"     ✅ Pyramid {opened_now}/{burst} @ {lot:.2f} lot")
                        if opened_now:
                            next_add_profit += PROFIT_ADD_STEP
                            positions = list(mt5.positions_get(magic=MAGIC) or [])
                            basket_tp, basket_sl = get_dynamic_tp_sl(None, positions)
                            prev_position_count = len(positions)

                if positions:
                    print_status(positions, tp, sl, next_add_profit)
                else:
                    # Basket was closed by reversal; fall through to wait logic below.
                    pass

            if not positions:
                scan += 1
                print(f"\nScan #{scan} | {datetime.now().strftime('%H:%M:%S')}")
                print(f"  {SYMBOL}: PRIMARY SIGNAL = {signal_text}")
                print(f"  CONTEXT: M15={m15_context or 'NONE'} | M30={m30_context or 'NONE'}")

                if reversal_wait:
                    # We intentionally do not immediately flip after closing.
                    # The next loop must see a NEW structural signal in the opposite direction.
                    if signal and signal['direction'] != reversal_origin:
                        if structure_signal_is_new(signal, last_consumed_signal_key):
                            print(
                                f"  ✅ REVERSAL WAIT COMPLETE: {reversal_origin} -> {signal['direction']}"
                            )
                            print("  🚀 Fresh BOS+RETEST detected — re-entry unlocked")
                            reversal_wait = False
                            reversal_origin = None
                        else:
                            print("  ⏸️ Same structural signal already consumed — waiting for a NEW BOS+RETEST")
                            time.sleep(CHECK_EVERY)
                            continue
                    else:
                        print(
                            f"  ⏸️ REVERSAL WAIT: closed {reversal_origin or 'previous'} basket. "
                            f"Waiting for a fresh opposite BOS+RETEST."
                        )
                        time.sleep(CHECK_EVERY)
                        continue

                if news_blackout:
                    print("  📰 News blackout — holding off new entries")
                elif not in_trading_session():
                    print("  🌙 Outside trading session — holding off new entries")
                elif not spread_ok():
                    print("  📏 Spread too wide — holding off new entries")
                elif signal and structure_signal_is_new(signal, last_consumed_signal_key):
                    direction = signal['direction']
                    print(
                        f"  🎯 BOS+RETEST CONFIRMED: {direction} | broken level {signal['level']:.2f}"
                    )
                    print(
                        f"  📊 M15/M30 context: {m15_context or 'NONE'} / {m30_context or 'NONE'} "
                        f"(context does NOT veto this signal)"
                    )
                    print(f"  🚀 INITIAL BATCH: opening {min(INITIAL_ENTRY_TRADES, MAX_TRADES)} {direction} positions...")

                    batch_size = min(INITIAL_ENTRY_TRADES, MAX_TRADES)
                    opened = 0
                    for i in range(batch_size):
                        lot = get_pyramid_lot(i)
                        if open_trade(direction, lot):
                            opened += 1
                            print(f"     ✅ Initial position {opened}/{batch_size} @ {lot:.2f} lot")

                    last_consumed_signal_key = signal_key
                    if opened:
                        current_direction = direction
                        peak_profit = 0.0
                        partial_taken = False
                        basket_tp = BASKET_TP
                        basket_sl = MAX_BASKET_SL
                        prev_position_count = opened
                        next_add_profit = PROFIT_ADD_STEP
                        positions = list(mt5.positions_get(magic=MAGIC) or [])
                        print(f"  📦 Initial basket: {len(positions)}/{MAX_TRADES} positions")
                    else:
                        print("  ⚠️ Initial batch failed — will retry on a NEW signal")
                else:
                    print("  ⏳ No new BOS+RETEST yet — waiting for price structure to reveal itself")

            time.sleep(CHECK_EVERY)

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped.")
        info = mt5.account_info()
        if info:
            print(f"Final Balance: ${info.balance:.2f}")
        mt5.shutdown()
        input("Press Enter to exit...")


if __name__ == "__main__":
    run()
