# NSE Positional Trader V5.2.2

Phone-first NSE positional-trading research / paper-trading app built with Streamlit.

## V5.2.2 changes

1. **Scoring normalization fixed**
   - Base score components are exactly 90 points: Trend 25 + Momentum 15 + Relative Strength 20 + Volume/Breakout 15 + Fundamentals 15.
   - Market regime adds up to 5 points separately.
   - Event risk is a penalty of up to 10 points.
   - Final score is normalized against the maximum score available in the current regime, so 100 really means the maximum achievable score for that regime.

2. **Sector relative strength fixed**
   - Sector RS is calculated against the median 63-day return of eligible stocks in the same mapped sector.
   - A stock is never compared against itself as its only sector peer.
   - If there are fewer than two eligible sector peers, Sector RS is explicitly treated as unavailable and receives a neutral 5/10 rather than a misleading 0 or self-comparison.

3. **Smarter stop-loss / target logic**
   - Compares a 2×ATR stop with a 20-session swing-low stop buffered by 0.25×ATR.
   - Uses the tighter valid structural stop when it falls within configured 1%–12% distance limits.
   - Falls back to a bounded ATR stop if both structural choices are unsuitable.
   - Target remains a configurable 2R by default.
   - Displays Stop Method, Stop Distance %, Risk/Share and R Multiple.

4. **Liquidity filter added**
   - Latest close must be **≤ ₹15,000**.
   - 20-day average traded value must be **≥ ₹5 crore/day**.
   - 20-day median traded value must be **≥ ₹2 crore/day**.
   - At least **90% of the last 20 sessions must have positive volume**.
   - Illiquid / price-ineligible stocks are excluded from the Top 20 / Top 6 candidate pool.

5. **Data-health diagnostics**
   - Shows universe size, price data availability, price/liquidity eligible count, exclusions, rankable count, enrichment count, failures and Top 20 returned.

6. **Fundamentals display fix retained**
   - Handles scalar, list, array and dictionary values safely.

## Default workflow

NSE universe → price/volume validation → liquidity/price filter → technical scoring → fundamentals/event enrichment → Top 20 → Top 6 priority → risk calculation → AI second opinion → paper portfolio → journal.

## Important

- This is research/paper-trading software, not a live broker execution system.
- Public/free market-data sources can be delayed, incomplete, stale or rate-limited.
- Corporate announcements should be verified against the original NSE/company disclosure.
- A Top 20 or Top 6 ranking is not a guaranteed buy signal.
