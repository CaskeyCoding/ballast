---
title: How to Read a Backtest Honestly
source: Caskey investing methodology, public educational summary (caskeycoding.com)
url: https://www.caskeycoding.com/blog/backtesting-without-fooling-yourself
published: 2026-06-09
license: original educational content (repository author)
attribution_string: Eric Caskey, caskeycoding.com
---

# Reading a Backtest Honestly

A backtest tests an investing rule against historical data. It is easy to make one look impressive
and hard to make one trustworthy. The most useful way to think about a backtest is that its real job
is not to find an edge, it is to stop you from believing in an edge that is not actually there.

Several common mistakes make a backtest look better than reality. Survivorship bias tests only the
companies or funds that lasted, ignoring those that failed. Look-ahead bias uses information that
would not have been available at the time. Trying many variations and keeping only the best, often
called multiple testing or the garden of forking paths, all but guarantees a good-looking result by
chance. Ignoring trading costs reports gross returns that no real investor would have kept.

The central discipline is out-of-sample testing: reserve data the rule never saw and check whether
the result holds there. A pattern that only appears in the data used to build the rule is the
default outcome of searching, not a discovery. Spending effort on honesty, rather than on a smoother
curve, is what separates a real finding from self-deception.
